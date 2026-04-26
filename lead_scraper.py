"""
FOMAD - Episode 1 (Scripts / Automation Playlist)
Build a Python Lead Scraper with AI CV Matching

What it does:
  1. Searches Google Maps for businesses by type and country
  2. Extracts: name, phone, address, website, rating, category
  3. Reads your CV from a PDF file
  4. AI agent (OpenAI) analyses every company against your CV
  5. Returns a ranked list of the best companies to approach and why
  6. Exports the full lead list to CSV

Requirements:
  pip install requests pandas pdfplumber openai python-dotenv rich
"""

import os
import csv
import time
import requests
import pdfplumber
import pandas as pd
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console
from rich.rule import Rule
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich import box

console = Console()

# ─────────────────────────────────────────────
#  LOAD ENVIRONMENT VARIABLES
# ─────────────────────────────────────────────

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not GOOGLE_API_KEY or not OPENAI_API_KEY:
    console.print("[bold red]✖  Missing API keys. Check your .env file.[/bold red]")
    raise SystemExit(1)

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

SEARCH_TERM  = "AI Automation agency"   # type of business to find
COUNTRY      = "Finland"                # any country in the world
MAX_RESULTS  = 60                       # up to 60 (Google returns 20 per page)
CV_FILE      = "my_cv.pdf"             # your CV — place it in this folder
OUTPUT_FILE  = f"leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

PLACES_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"


# ─────────────────────────────────────────────
#  STEP 1 — SEARCH GOOGLE MAPS
# ─────────────────────────────────────────────

def search_places(query: str, country: str) -> list[dict]:
    """Search Google Maps for businesses. Handles pagination up to 60 results."""
    all_results  = []
    is_first_page = True
    params = {
        "query": f"{query} in {country}",
        "key":   GOOGLE_API_KEY,
    }

    while len(all_results) < MAX_RESULTS:
        response = requests.get(PLACES_SEARCH_URL, params=params, timeout=15)
        response.raise_for_status()
        data   = response.json()
        status = data.get("status")

        if status == "INVALID_REQUEST" and not is_first_page:
            console.print(f"  [yellow]⚠  Pagination stopped (token expired). Keeping {len(all_results)} results.[/yellow]")
            break

        if status not in ("OK", "ZERO_RESULTS"):
            raise RuntimeError(f"Google Maps error: {status} — {data.get('error_message', '')}")

        results = data.get("results", [])
        all_results.extend(results)
        console.print(f"  [cyan]↓  Fetched {len(results)} results[/cyan]  [dim](total: {len(all_results)})[/dim]")
        is_first_page = False

        next_token = data.get("next_page_token")
        if not next_token or len(all_results) >= MAX_RESULTS:
            break

        time.sleep(3)
        params = {"pagetoken": next_token, "key": GOOGLE_API_KEY}

    return all_results[:MAX_RESULTS]


# ─────────────────────────────────────────────
#  STEP 2 — FETCH PLACE DETAILS
# ─────────────────────────────────────────────

def get_place_details(place_id: str) -> dict:
    """Fetch phone, website, and address for a place."""
    params = {
        "place_id": place_id,
        "fields":   "name,formatted_phone_number,website,formatted_address,types,rating",
        "key":      GOOGLE_API_KEY,
    }
    response = requests.get(PLACES_DETAIL_URL, params=params, timeout=15)
    response.raise_for_status()
    return response.json().get("result", {})


# ─────────────────────────────────────────────
#  STEP 3 — BUILD LEAD LIST
# ─────────────────────────────────────────────

def build_leads(places: list[dict]) -> list[dict]:
    """Fetch details for every place and return a list of lead dicts."""
    leads = []

    for i, place in enumerate(places, 1):
        place_id = place.get("place_id")
        console.print(f"  [dim]{i}/{len(places)}[/dim]  [white]{place.get('name', '')}[/white]")

        details = get_place_details(place_id)
        leads.append({
            "name":     details.get("name", ""),
            "phone":    details.get("formatted_phone_number", ""),
            "address":  details.get("formatted_address", ""),
            "website":  details.get("website", ""),
            "rating":   details.get("rating", ""),
            "category": ", ".join(details.get("types", [])[:2]).replace("_", " "),
        })
        time.sleep(0.1)

    return leads


# ─────────────────────────────────────────────
#  STEP 4 — CLEAN AND DEDUPLICATE
# ─────────────────────────────────────────────

def clean_leads(raw: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(raw)
    before = len(df)
    df.drop_duplicates(subset=["name", "phone"], inplace=True)
    df.dropna(subset=["name"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    console.print(f"\n  [green]✔  Cleaned:[/green] {before} raw → [bold green]{len(df)} unique leads[/bold green]")
    return df


# ─────────────────────────────────────────────
#  STEP 5 — EXPORT TO CSV
# ─────────────────────────────────────────────

def export_csv(df: pd.DataFrame, filename: str):
    df.to_csv(filename, index=False, quoting=csv.QUOTE_ALL)
    console.print(f"  [green]✔  Saved:[/green] [bold]{filename}[/bold]  [dim]({len(df)} leads)[/dim]")


# ─────────────────────────────────────────────
#  STEP 6 — READ CV FROM PDF
# ─────────────────────────────────────────────

def read_cv(filepath: str) -> str:
    """Extract all text from the CV PDF."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CV not found: {filepath}\nPlace your CV PDF in the same folder as this script.")

    text = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            content = page.extract_text()
            if content:
                text.append(content)

    full_text = "\n".join(text).strip()
    console.print(f"  [green]✔  CV loaded:[/green] [bold]{len(full_text)} characters[/bold] across [bold]{len(text)} page(s)[/bold]")
    return full_text


# ─────────────────────────────────────────────
#  STEP 7 — AI AGENT: MATCH CV TO COMPANIES
# ─────────────────────────────────────────────

def analyse_with_ai(cv_text: str, df: pd.DataFrame) -> str:
    """
    Send the CV and company list to OpenAI.
    Returns a ranked analysis of which companies to approach and why.
    """
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Format the company list for the prompt
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
If a company is a poor match, you don't need to include it.

─── CV ───────────────────────────────────────────────
{cv_text}

─── COMPANIES ────────────────────────────────────────
{companies_text}
"""

    console.print("  [magenta]⟳  Sending to OpenAI for analysis...[/magenta]")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    return response.choices[0].message.content


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    console.print(Panel(
        f"[bold white]FOMAD Lead Scraper  —  Google Maps + AI[/bold white]\n"
        f"[dim]Searching :[/dim] [cyan]{SEARCH_TERM}[/cyan]\n"
        f"[dim]Country   :[/dim] [cyan]{COUNTRY}[/cyan]\n"
        f"[dim]Output    :[/dim] [cyan]{OUTPUT_FILE}[/cyan]",
        border_style="bright_blue",
        padding=(0, 2),
    ))

    # 1 — Scrape
    console.print(Rule("[bold bright_blue][1/5] Searching Google Maps[/bold bright_blue]"))
    places = search_places(SEARCH_TERM, COUNTRY)
    if not places:
        console.print("  [red]✖  No results found. Try a different search term.[/red]")
        return

    # 2 — Details
    console.print(Rule(f"[bold bright_blue][2/5] Fetching details for {len(places)} businesses[/bold bright_blue]"))
    raw_leads = build_leads(places)

    # 3 — Clean
    console.print(Rule("[bold bright_blue][3/5] Cleaning data[/bold bright_blue]"))
    df = clean_leads(raw_leads)

    # 4 — Export
    console.print(Rule("[bold bright_blue][4/5] Exporting CSV[/bold bright_blue]"))
    export_csv(df, OUTPUT_FILE)

    # 4b — Print lead table preview
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold white", min_width=60)
    table.add_column("Name",    style="white",      max_width=28)
    table.add_column("Phone",   style="cyan",        max_width=16)
    table.add_column("Rating",  style="yellow",      max_width=6,  justify="center")
    table.add_column("Website", style="dim",         max_width=30)
    for _, row in df.head(5).iterrows():
        table.add_row(str(row["name"]), str(row["phone"]), str(row["rating"]), str(row["website"]))
    console.print("\n  [dim]Preview — first 5 leads:[/dim]")
    console.print(table)

    # 5 — AI analysis
    console.print(Rule("[bold bright_blue][5/5] AI CV Analysis[/bold bright_blue]"))
    cv_text  = read_cv(CV_FILE)
    analysis = analyse_with_ai(cv_text, df)

    # Save report
    report_file = OUTPUT_FILE.replace(".csv", "_ai_report.txt")
    with open(report_file, "w") as f:
        f.write(f"FOMAD AI Match Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Search: {SEARCH_TERM} in {COUNTRY}\n")
        f.write("=" * 56 + "\n\n")
        f.write(analysis)

    # Print AI report
    console.print(Rule("[bold magenta]AI Match Report[/bold magenta]"))
    console.print(Markdown(analysis), style="white")
    console.print(f"\n  [green]✔  AI report →[/green] [bold]{report_file}[/bold]")
    console.print(f"  [green]✔  Lead list →[/green] [bold]{OUTPUT_FILE}[/bold]")


if __name__ == "__main__":
    main()
