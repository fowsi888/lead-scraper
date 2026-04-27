import os
import json
import re
import threading
from collections import Counter

import markdown as md_lib
from django.conf import settings
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.html import mark_safe
from django.views.decorators.http import require_POST

from .models import ScraperJob
from .scraper_engine import run_scraper_job


def home(request):
    return render(request, 'scraper/home.html')


@require_POST
def start_job(request):
    cv_file = request.FILES.get('cv_file')
    search_term = request.POST.get('search_term', '').strip()
    country = request.POST.get('country', '').strip()
    max_results = min(int(request.POST.get('max_results', 60)), 60)

    errors = []
    if not cv_file:
        errors.append("Please upload your CV as a PDF file.")
    elif not cv_file.name.lower().endswith('.pdf'):
        errors.append("Only PDF files are accepted.")
    if not search_term:
        errors.append("Please enter a search term.")
    if not country:
        errors.append("Please enter a country.")

    if errors:
        return render(request, 'scraper/home.html', {'errors': errors,
                                                      'search_term': search_term,
                                                      'country': country})

    job = ScraperJob.objects.create(
        search_term=search_term,
        country=country,
        max_results=max_results,
    )

    cv_dir = os.path.join(settings.MEDIA_ROOT, 'cvs')
    os.makedirs(cv_dir, exist_ok=True)
    cv_path = os.path.join(cv_dir, f'{job.job_id}.pdf')
    with open(cv_path, 'wb') as f:
        for chunk in cv_file.chunks():
            f.write(chunk)

    job.cv_path = cv_path
    job.save()

    thread = threading.Thread(target=run_scraper_job, args=(str(job.job_id),), daemon=True)
    thread.start()

    return redirect('progress', job_id=str(job.job_id))


def progress(request, job_id):
    job = get_object_or_404(ScraperJob, job_id=job_id)
    return render(request, 'scraper/progress.html', {'job': job})


def job_status_api(request, job_id):
    job = get_object_or_404(ScraperJob, job_id=job_id)
    redirect_url = None
    if job.status == 'complete':
        redirect_url = f'/results/{job_id}/'
    elif job.status == 'error':
        redirect_url = f'/error/{job_id}/'

    return JsonResponse({
        'status': job.status,
        'progress': job.progress,
        'message': job.progress_message,
        'log': job.log_messages or [],
        'total_found': job.total_found,
        'total_leads': job.total_leads,
        'redirect_url': redirect_url,
    })


def results(request, job_id):
    job = get_object_or_404(ScraperJob, job_id=job_id)
    if job.status not in ('complete', 'error'):
        return redirect('progress', job_id=job_id)

    leads = job.leads_json or []

    def _str(val):
        """Return stripped string; treat None/NaN/float as empty."""
        if val is None:
            return ''
        try:
            import math
            if isinstance(val, float) and math.isnan(val):
                return ''
        except Exception:
            pass
        return str(val).strip()

    # Chart 1: rating distribution (1–5 stars)
    ratings = []
    for l in leads:
        raw = _str(l.get('rating'))
        try:
            v = float(raw)
            if v > 0:
                ratings.append(v)
        except ValueError:
            pass
    rating_buckets = [0, 0, 0, 0, 0]
    for r in ratings:
        bucket = max(0, min(int(r) - 1, 4))
        rating_buckets[bucket] += 1

    # Outreach stats
    with_website = sum(1 for l in leads if _str(l.get('website')).startswith('http'))
    with_phone = sum(1 for l in leads if _str(l.get('phone')))

    # Stats
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
    # Use len(leads) as the authoritative count — more reliable than job.total_leads
    # (the DB field is written by a background thread and can silently fail)
    total_leads_display = len(leads)

    # Render markdown AI analysis to HTML
    ai_html = ''
    if job.ai_analysis:
        ai_html = md_lib.markdown(
            job.ai_analysis,
            extensions=['extra', 'sane_lists', 'nl2br'],
        )

    # Extract confidence scores for summary
    scores = [int(m) for m in re.findall(r'(\d+)/10', job.ai_analysis or '')]
    avg_confidence = round(sum(scores) / len(scores), 1) if scores else 0
    match_count = len(scores)

    # Top 5 leads for spotlight card — best rated first, then website presence
    def _lead_sort(lead):
        try:
            r = float(_str(lead.get('rating'))) if _str(lead.get('rating')) else 0
        except ValueError:
            r = 0
        has_web = 1 if _str(lead.get('website')).startswith('http') else 0
        return (-r, -has_web)

    top_leads_preview = sorted(leads, key=_lead_sort)[:5]

    # Ready to Contact — leads with both website and phone, sorted by rating
    ready_to_contact = sorted(
        [l for l in leads if _str(l.get('website')).startswith('http') and _str(l.get('phone'))],
        key=_lead_sort
    )[:5]

    # Outreach percentages for progress bars
    total = len(leads) or 1
    website_pct = round(with_website / total * 100)
    phone_pct = round(with_phone / total * 100)

    return render(request, 'scraper/results.html', {
        'job': job,
        'leads': leads,
        'total_leads_display': total_leads_display,
        'ai_analysis_html': mark_safe(ai_html),
        'avg_rating': avg_rating,
        'with_website': with_website,
        'with_phone': with_phone,
        'website_pct': website_pct,
        'phone_pct': phone_pct,
        'top_leads_preview': top_leads_preview,
        'ready_to_contact': ready_to_contact,
        'avg_confidence': avg_confidence,
        'match_count': match_count,
    })


def error_view(request, job_id):
    job = get_object_or_404(ScraperJob, job_id=job_id)
    return render(request, 'scraper/error.html', {'job': job})


def download_csv(request, job_id):
    job = get_object_or_404(ScraperJob, job_id=job_id)
    if not job.csv_path or not os.path.exists(job.csv_path):
        raise Http404("CSV file not found.")
    with open(job.csv_path, 'r', encoding='utf-8') as f:
        content = f.read()
    filename = f"leads_{job.search_term}_{job.country}.csv".replace(' ', '_')
    response = HttpResponse(content, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
