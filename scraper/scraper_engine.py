import os
import csv
import math
import sys
import time
import traceback
import requests
import pdfplumber
import pandas as pd
from datetime import datetime
from openai import OpenAI
from django.db import close_old_connections
from django.conf import settings as django_settings


PLACES_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Google always injects these generic types — filter them out for meaningful categories
_GENERIC_TYPES = {
    "point_of_interest", "establishment", "business", "local_business",
    "food", "store", "health", "finance", "service", "premise",
    "general_contractor", "geocode",
}


def _pick_category(types: list) -> str:
    """Return the most specific business type, skipping generic Google placeholders.
    Returns empty string when every type is generic (handled as 'no category' in view)."""
    specific = [t for t in types if t not in _GENERIC_TYPES]
    if not specific:
        return ""   # all generic → view will mark has_categories=False
    return specific[0].replace("_", " ").title()


# Major cities per country — used to break country-wide searches into city searches
# so Google Places returns real results instead of a tiny handful.
_CITIES = {
    "usa":            ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
                       "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
                       "Austin", "Jacksonville", "Seattle", "Denver", "Boston",
                       "Miami", "Atlanta", "Minneapolis", "Portland", "Las Vegas"],
    "uk":             ["London", "Manchester", "Birmingham", "Leeds", "Glasgow",
                       "Sheffield", "Liverpool", "Edinburgh", "Bristol", "Nottingham"],
    "australia":      ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide",
                       "Gold Coast", "Canberra", "Hobart", "Darwin", "Newcastle"],
    "canada":         ["Toronto", "Montreal", "Vancouver", "Calgary", "Edmonton",
                       "Ottawa", "Winnipeg", "Quebec City", "Hamilton", "Victoria"],
    "germany":        ["Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt",
                       "Stuttgart", "Düsseldorf", "Leipzig", "Dortmund", "Bremen"],
    "france":         ["Paris", "Lyon", "Marseille", "Toulouse", "Bordeaux",
                       "Nice", "Nantes", "Strasbourg", "Montpellier", "Rennes"],
    "netherlands":    ["Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven",
                       "Groningen", "Tilburg", "Almere", "Breda", "Nijmegen"],
    "spain":          ["Madrid", "Barcelona", "Valencia", "Seville", "Bilbao",
                       "Zaragoza", "Málaga", "Murcia", "Las Palmas", "Valladolid"],
    "italy":          ["Rome", "Milan", "Naples", "Turin", "Palermo",
                       "Genoa", "Bologna", "Florence", "Bari", "Catania"],
    "sweden":         ["Stockholm", "Gothenburg", "Malmö", "Uppsala", "Linköping",
                       "Örebro", "Västerås", "Helsingborg", "Norrköping", "Jönköping"],
    "norway":         ["Oslo", "Bergen", "Trondheim", "Stavanger", "Drammen",
                       "Fredrikstad", "Kristiansand", "Sandnes", "Tromsø", "Sarpsborg"],
    "denmark":        ["Copenhagen", "Aarhus", "Odense", "Aalborg", "Esbjerg",
                       "Randers", "Kolding", "Horsens", "Vejle", "Roskilde"],
    "finland":        ["Helsinki", "Espoo", "Tampere", "Vantaa", "Oulu",
                       "Turku", "Jyväskylä", "Lahti", "Kuopio", "Pori"],
    "ireland":        ["Dublin", "Cork", "Limerick", "Galway", "Waterford",
                       "Drogheda", "Dundalk", "Swords", "Bray", "Navan"],
    "india":          ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
                       "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat"],
    "uae":            ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah"],
    "singapore":      ["Singapore"],
    "south africa":   ["Johannesburg", "Cape Town", "Durban", "Pretoria", "Port Elizabeth"],
    "new zealand":    ["Auckland", "Wellington", "Christchurch", "Hamilton", "Tauranga"],
    "poland":         ["Warsaw", "Kraków", "Łódź", "Wrocław", "Poznań",
                       "Gdańsk", "Szczecin", "Katowice", "Lublin", "Bydgoszcz"],
    "brazil":         ["São Paulo", "Rio de Janeiro", "Brasília", "Salvador", "Fortaleza",
                       "Belo Horizonte", "Manaus", "Curitiba", "Recife", "Porto Alegre"],
    "mexico":         ["Mexico City", "Guadalajara", "Monterrey", "Puebla", "Tijuana",
                       "León", "Juárez", "Zapopan", "Mérida", "San Luis Potosí"],
}

_COUNTRY_ALIASES = {
    "united states": "usa", "united states of america": "usa", "us": "usa",
    "united kingdom": "uk", "great britain": "uk", "england": "uk",
    "the netherlands": "netherlands", "holland": "netherlands",
    "south korea": "south korea",
    "uae": "uae", "united arab emirates": "uae",
}

def _normalise_country(country: str) -> str:
    key = country.strip().lower().rstrip(".")
    return _COUNTRY_ALIASES.get(key, key)


def _fetch_pages(query_str: str, api_key: str, seen_ids: set, max_results: int) -> list:
    """Fetch up to 3 pages for one query string.  Deduplicates via seen_ids (mutated in-place).
    Returns list of new unique places."""
    collected = []
    params = {"query": query_str, "key": api_key}
    for _ in range(3):
        # Stop if we already have enough across all cities
        if len(seen_ids) >= max_results:
            break
        try:
            resp = requests.get(PLACES_SEARCH_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        status = data.get("status")
        if status in ("ZERO_RESULTS", "INVALID_REQUEST") or status != "OK":
            break

        for place in data.get("results", []):
            pid = place.get("place_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                collected.append(place)

        next_token = data.get("next_page_token")
        if not next_token:
            break
        time.sleep(3)
        params = {"pagetoken": next_token, "key": api_key}

    return collected


def search_places(query, country, api_key, max_results=60, progress_cb=None):
    """Search Google Places, using city-by-city queries when the country has
    major cities defined — this gives far more results than a single country query."""
    seen_ids: set = set()
    all_results: list = []

    country_key = _normalise_country(country)
    cities = _CITIES.get(country_key, [])

    if cities:
        # City-by-city strategy — each city can yield up to 60 results (3 pages × 20)
        for i, city in enumerate(cities):
            if len(all_results) >= max_results:
                break
            q = f"{query} in {city}, {country}"
            if progress_cb:
                progress_cb(f"Searching {city} ({len(all_results)}/{max_results} leads so far)")
            new = _fetch_pages(q, api_key, seen_ids, max_results)
            all_results.extend(new)
            if new:
                time.sleep(0.3)
    else:
        # Fallback: single country-level query
        if progress_cb:
            progress_cb(f"Searching {country} (no city list — trying country-wide)")
        new = _fetch_pages(f"{query} in {country}", api_key, seen_ids, max_results)
        all_results.extend(new)

    return all_results[:max_results]


def get_place_details(place_id, api_key):
    params = {
        "place_id": place_id,
        "fields": "name,formatted_phone_number,website,formatted_address,types,rating",
        "key": api_key,
    }
    response = requests.get(PLACES_DETAIL_URL, params=params, timeout=15)
    response.raise_for_status()
    return response.json().get("result", {})


def clean_leads(raw):
    df = pd.DataFrame(raw)
    df.drop_duplicates(subset=["name", "phone"], inplace=True)
    df.dropna(subset=["name"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def read_cv(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CV not found: {filepath}")
    text = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            content = page.extract_text()
            if content:
                text.append(content)
    return "\n".join(text).strip()


def analyse_with_ai(cv_text, df, api_key):
    client = OpenAI(api_key=api_key)

    companies_text = ""
    for i, row in df.iterrows():
        companies_text += (
            f"{i + 1}. {row['name']}\n"
            f"   Category : {row['category']}\n"
            f"   Address  : {row['address']}\n"
            f"   Website  : {row['website']}\n"
            f"   Phone    : {row['phone']}\n"
            f"   Rating   : {row['rating']}\n\n"
        )

    prompt = f"""You are a career and business development advisor.

Below is a candidate's CV, followed by a list of companies scraped from Google Maps.

Your job:
1. Analyse the candidate's skills, experience, and background from the CV
2. Review each company — its name, category, and any context you can infer
3. Identify which companies are the BEST match for this candidate to approach
   (for freelance work, a job, or a client relationship)
4. Return a ranked list of the TOP matches with:
   - Company name
   - Why it's a good match (specific to the CV)
   - What service or role the candidate should pitch
   - A confidence score out of 10

Be specific. Reference actual skills or experience from the CV.
Format each match as:
## [Rank]. [Company Name]
**Why it's a good match:** ...
**What to pitch:** ...
**Confidence:** X/10

─── CV ───────────────────────────────────────────────
{cv_text}

─── COMPANIES ────────────────────────────────────────
{companies_text}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content


def run_scraper_job(job_id_str):
    """Entry point for the background thread."""
    close_old_connections()

    from .models import ScraperJob

    def update(progress, message, status=None, extra=None):
        try:
            job = ScraperJob.objects.get(job_id=job_id_str)
            job.progress = progress
            job.progress_message = message
            if status:
                job.status = status
            log_entry = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "msg": message,
                "level": "success" if status == "complete" else ("error" if status == "error" else "info"),
            }
            log = list(job.log_messages or [])
            log.append(log_entry)
            job.log_messages = log[-60:]
            if extra:
                for k, v in extra.items():
                    setattr(job, k, v)
            job.save()
        except Exception as _e:
            print(f"[scraper update ERROR] {_e}", file=sys.stderr)

    try:
        job = ScraperJob.objects.get(job_id=job_id_str)
        google_api_key = django_settings.GOOGLE_API_KEY
        openai_api_key = django_settings.OPENAI_API_KEY
        search_term = job.search_term
        country = job.country
        max_results = job.max_results
        cv_path = job.cv_path

        if not google_api_key or not openai_api_key:
            update(0, "Missing API keys. Check your .env file.", "error")
            return

        # Step 1 — Search (city-by-city for countries with a city list)
        update(5, f'Searching Google Maps for "{search_term}" in {country}', "searching")

        def _search_progress(msg):
            update(8, msg)

        places = search_places(search_term, country, google_api_key, max_results,
                               progress_cb=_search_progress)
        update(15, f"Found {len(places)} businesses across Google Maps",
               extra={"total_found": len(places)})

        if not places:
            update(0, "No results found. Try a different search term.", "error")
            return

        # Step 2 — Fetch details
        update(20, f"Starting to fetch details for {len(places)} businesses", "fetching")
        raw_leads = []
        for i, place in enumerate(places):
            pct = 20 + int((i / len(places)) * 33)
            name = place.get("name", "")
            update(pct, f"Fetching {i + 1}/{len(places)}: {name}")
            details = get_place_details(place.get("place_id"), google_api_key)
            raw_leads.append({
                "name":     details.get("name") or "",
                "phone":    details.get("formatted_phone_number") or "",
                "address":  details.get("formatted_address") or "",
                "website":  details.get("website") or "",
                # Keep as float or None — never use "" so pandas won't mix types
                "rating":   details.get("rating"),
                "category": _pick_category(details.get("types", [])),
            })
            time.sleep(0.1)

        # Step 3 — Clean
        update(55, "Cleaning and deduplicating leads data", "cleaning")
        df = clean_leads(raw_leads)

        # Sanitise: pandas converts None in numeric columns to float NaN.
        # json.dumps(NaN) writes the unquoted literal NaN which is not valid JSON,
        # so json.loads crashes on read-back → leads_json becomes None.
        # Replace every NaN/inf with None so they serialise as JSON null.
        def _safe(v):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            return v

        leads_list = [
            {k: _safe(v) for k, v in row.items()}
            for row in df.to_dict("records")
        ]

        update(60, f"Cleaned to {len(df)} unique leads",
               extra={"total_leads": len(df), "leads_json": leads_list})

        # Export CSV
        csv_filename = f"leads_{job_id_str[:8]}.csv"
        csv_export_path = os.path.join(django_settings.MEDIA_ROOT, "exports", csv_filename)
        os.makedirs(os.path.dirname(csv_export_path), exist_ok=True)
        df.to_csv(csv_export_path, index=False, quoting=csv.QUOTE_ALL)
        update(63, f"Exported {len(df)} leads to CSV", extra={"csv_path": csv_export_path})

        # Step 4 — Read CV
        update(65, "Reading your Business Profile / CV", "reading_cv")
        cv_text = read_cv(cv_path)
        update(70, f"Business Profile / CV loaded: {len(cv_text):,} characters extracted")

        # Step 5 — AI analysis
        update(73, "AI agent is analysing your Business Profile / CV against each company...", "analyzing")
        analysis = analyse_with_ai(cv_text, df, openai_api_key)

        update(100, "Analysis complete! All done.", "complete",
               extra={"ai_analysis": analysis, "leads_json": leads_list,
                      "total_leads": len(leads_list)})

    except Exception as e:
        tb = traceback.format_exc()
        update(0, f"Error: {str(e)}", "error", extra={"error_message": tb})
