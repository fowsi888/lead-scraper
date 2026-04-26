# FOMAD Lead Scraper

A Django web app that finds local business leads from Google Maps, scores them against your CV using AI, and exports everything to CSV — built for the **FOMAD YouTube channel**.

---

## Features

- Search any business type in any country via the Google Maps Places API
- Upload your CV (PDF) — AI matches each lead to your skills and scores it 1–10
- Clean results dashboard with rating charts, outreach quality stats, and AI analysis
- One-click CSV export
- Runs fully locally — your data never leaves your machine

---

## Quick Start

```bash
# 1. Clone & enter the project
git clone https://github.com/your-username/lead-scraper.git
cd lead-scraper

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and add your API keys

# 5. Apply migrations and start the server
python manage.py migrate
python manage.py runserver
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|---|---|
| `GOOGLE_API_KEY` | Google Maps Places API key |
| `OPENAI_API_KEY` | OpenAI API key (GPT-4 for CV matching) |

---

## Tech Stack

- **Backend:** Django 4.2+, Python 3.10+
- **AI:** OpenAI GPT-4 (CV-to-lead matching)
- **Data:** Google Maps Places API, pdfplumber, pandas
- **Frontend:** Vanilla JS, Chart.js, Font Awesome

---

## ⚠️ Disclaimer

This tool uses the **Google Maps Places API** — a legitimate, paid API service — to retrieve publicly listed business information. It does **not** scrape or crawl Google's website in violation of their Terms of Service.

You are solely responsible for:

- Complying with [Google Maps Platform Terms of Service](https://cloud.google.com/maps-platform/terms)
- Ensuring your use of collected data respects applicable privacy laws (GDPR, CCPA, etc.)
- Using outreach data ethically and lawfully in your region
- Any business or legal outcomes resulting from your use of this tool

This software is provided **for educational and automation purposes only**. The author makes no warranties and accepts no liability for how this tool is used.

---

## 📞 Contact & Support

**Website:** [fomad.net](https://fomad.net)  
**YouTube:** [FOMAD](https://youtube.com/@FOMAD)  
**Email:** [info@fomad.net](mailto:info@fomad.net)

Found a bug or have a feature request? Open an issue on GitHub or reach out via email.

---

## 📄 License

This project is free to use under the **MIT License**. You can:

- Use it for personal projects
- Use it for commercial projects
- Modify the code
- Distribute it
- Sell services built with it

See [LICENSE](LICENSE) for the full text.
