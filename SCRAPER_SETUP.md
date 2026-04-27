# MortgageWatch.ie — Scraper Setup Guide

## How it works

Every day at 07:00 UTC (08:00 Irish time), GitHub Actions:

1. Spins up an Ubuntu virtual machine
2. Installs Python + Playwright (headless Chromium)
3. Runs `scrape.py` — visits each lender's rates page and extracts rates
4. Commits the updated `data/rates.json` to your GitHub repo
5. FTPs **only `rates.json`** to your Webworld.ie server
6. Your live site immediately serves the new rates

If a scraper fails for any lender, the **existing rates are kept** for that lender — the site never goes blank.

---

## One-time setup

### Step 1 — Create a GitHub repository

1. Go to [github.com](https://github.com) and sign in (or create a free account)
2. Click **New repository**
3. Name it `mortgagewatch` (or similar)
4. Set it to **Private**
5. Click **Create repository**

### Step 2 — Upload the site files

Upload the full site (all HTML, assets, data, scraper folders) to the repo.
The easiest way is to drag-and-drop into the GitHub web interface, or use GitHub Desktop.

Your repo structure should look like:

```
mortgagewatch/
├── .github/
│   └── workflows/
│       └── scrape.yml
├── assets/
│   ├── css/main.css
│   └── js/shared.js
├── data/
│   └── rates.json
├── lenders/
│   └── *.html
├── scraper/
│   ├── lenders/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── aib.py
│   │   ├── boi.py
│   │   ├── ptsb.py
│   │   ├── avant.py
│   │   ├── haven.py
│   │   ├── ebs.py
│   │   ├── ics.py
│   │   └── finance_ireland.py
│   ├── scrape.py
│   └── requirements.txt
├── index.html
├── rates.html
├── calculator.html
└── ...
```

### Step 3 — Add GitHub Secrets

The scraper needs your Webworld.ie FTP credentials to deploy. These are stored
as **encrypted GitHub Secrets** — they are never visible in logs.

1. In your GitHub repo, go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret** and add each of the following:

| Secret Name | Value | Example |
|---|---|---|
| `FTP_SERVER` | Your FTP hostname | `ftp.mortgagewatch.ie` or `ftp.webworld.ie` |
| `FTP_USERNAME` | Your FTP username | `mortgagewatch@mortgagewatch.ie` |
| `FTP_PASSWORD` | Your FTP password | (your Webworld password) |
| `FTP_REMOTE_PATH` | Remote root path | `/public_html/` or `/` |

> **Where to find these:** Log into your Webworld.ie control panel → FTP Accounts.
> The hostname, username and root directory are shown there.
> Use the same credentials you use in FileZilla.

### Step 4 — Test the workflow manually

1. In your repo, go to **Actions → Daily Rate Scrape & Deploy**
2. Click **Run workflow**
3. Tick **Dry run** on the first test (so nothing gets written to the server)
4. Watch the log — you should see each lender being scraped
5. Once you're happy it's working, run again without dry run

### Step 5 — Verify it's live

After a successful (non-dry-run) workflow, visit:
`https://mortgagewatch.ie/data/rates.json`

You should see the updated JSON with today's `last_updated` timestamp.

---

## Running locally (for testing)

```bash
cd scraper

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Scrape all lenders
python scrape.py --verbose

# Scrape one lender only
python scrape.py --lender aib --verbose

# Dry run (don't write output)
python scrape.py --dry-run --verbose
```

---

## Understanding scraper failures

Each lender scraper is independent. If one fails, the others continue.

Reasons a scraper might fail:

| Reason | What happens | Fix |
|---|---|---|
| Lender redesigned their rates page | Scraper returns no rates | Update the CSS selectors in that lender's `.py` file |
| Lender blocked the scraper IP | HTTP 403 or timeout | Add a longer delay or user-agent rotation |
| Rates are in a PDF | Can't parse PDF with Playwright | Download PDF, extract with `pdfplumber`, update scraper |
| Broker-only lender moved rates behind a login | Can't access | Switch to manual update for that lender |

Check `scraper/scrape.log` for details after each run.

---

## Updating a lender's rates manually

If a scraper fails for a specific lender, edit `data/rates.json` directly:

1. Open `data/rates.json`
2. Find the lender by `"id"`
3. Update the `"rate"` and `"aprc"` values and the `"last_updated"` timestamp
4. Commit and push — the GitHub Action will FTP it to the server

---

## Scraper schedule

The cron schedule `0 7 * * *` means **07:00 UTC every day**.

To change the time, edit `.github/workflows/scrape.yml`:

```yaml
- cron: '0 7 * * *'   # 07:00 UTC = 08:00 Irish time (winter) / 08:00 BST (summer)
```

[Cron syntax reference →](https://crontab.guru/)

---

## Estimated costs

| Service | Cost |
|---|---|
| GitHub Actions (public or private repo) | Free up to 2,000 minutes/month |
| This scraper runs in ~5–10 minutes/day | ~150–300 minutes/month — well within free tier |
| Playwright Chromium download | Cached after first run |

Total running cost: **€0/month**.
