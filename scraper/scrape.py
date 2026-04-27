"""
MortgageWatch.ie — Daily Rate Scraper (v2)
==========================================
Uses full-page text extraction with regex rather than CSS table selectors.
Irish bank sites render rates via JavaScript — we wait for the page to fully
settle then extract all percentage figures with surrounding context.

Usage:
  python scrape.py                  # scrape all lenders
  python scrape.py --lender aib     # scrape one lender only
  python scrape.py --dry-run        # scrape but don't write output
  python scrape.py --verbose        # debug logging
"""

import argparse
import json
import logging
import re
import sys
import copy
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data" / "rates.json"
LOG_FILE = Path(__file__).parent / "scrape.log"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"

# ── Lender definitions ──────────────────────────────────────────────────────
LENDERS = [
    {
        "id": "aib",
        "name": "AIB",
        "urls": [
            "https://aib.ie/mortgages/mortgage-rates",
            "https://www.aib.ie/mortgages/mortgage-rates",
        ],
        "cashback": None,
    },
    {
        "id": "boi",
        "name": "Bank of Ireland",
        "urls": [
            "https://www.bankofireland.com/mortgages/mortgage-rates/",
        ],
        "cashback": 2000,
    },
    {
        "id": "ptsb",
        "name": "PTSB",
        "urls": [
            "https://www.permanenttsb.ie/mortgages/our-rates/",
            "https://www.permanenttsb.ie/mortgages/mortgage-rates/",
        ],
        "cashback": 2000,
    },
    {
        "id": "avant",
        "name": "Avant Money",
        "urls": [
            "https://www.avantmoney.ie/mortgages/our-rates/",
            "https://www.avantmoney.ie/mortgages/",
        ],
        "cashback": None,
    },
    {
        "id": "haven",
        "name": "Haven Mortgages",
        "urls": [
            "https://www.havenmortgages.ie/mortgage-rates/",
            "https://www.havenmortgages.ie/rates/",
            "https://www.havenmortgages.ie/",
        ],
        "cashback": None,
    },
    {
        "id": "ebs",
        "name": "EBS",
        "urls": [
            "https://www.ebs.ie/mortgages/mortgage-rates",
            "https://www.ebs.ie/mortgages",
        ],
        "cashback": None,
    },
    {
        "id": "ics",
        "name": "ICS Mortgages",
        "urls": [
            "https://www.icsmortgages.ie/rates/",
            "https://www.icsmortgages.ie/",
        ],
        "cashback": None,
    },
    {
        "id": "finance-ireland",
        "name": "Finance Ireland",
        "urls": [
            "https://www.financeireland.ie/products/residential-mortgages/overview/",
            "https://www.financeireland.ie/products/residential-mortgages/rates/",
        ],
        "cashback": None,
    },
]

TERM_PATTERNS = [
    (r'\b1[\s-]year', 1),
    (r'\b2[\s-]year', 2),
    (r'\b3[\s-]year', 3),
    (r'\b4[\s-]year', 4),
    (r'\b5[\s-]year', 5),
    (r'\b7[\s-]year', 7),
    (r'\b10[\s-]year', 10),
    (r'\b15[\s-]year', 15),
    (r'\b20[\s-]year', 20),
    (r'\b25[\s-]year', 25),
    (r'\bone[\s-]year', 1),
    (r'\btwo[\s-]year', 2),
    (r'\bthree[\s-]year', 3),
    (r'\bfive[\s-]year', 5),
    (r'\bten[\s-]year', 10),
]


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        ],
    )


logger = logging.getLogger(__name__)


def dismiss_cookies(page):
    """Try common cookie banner patterns."""
    selectors = [
        "button:has-text('Accept All')",
        "button:has-text('Accept all')",
        "button:has-text('Accept Cookies')",
        "button:has-text('Accept cookies')",
        "button:has-text('Accept')",
        "button:has-text('OK')",
        "button:has-text('Agree')",
        "button[id*='accept']",
        "button[class*='accept']",
        "#onetrust-accept-btn-handler",
        ".cookie-accept",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click()
                page.wait_for_timeout(800)
                logger.debug(f"Dismissed cookie banner: {sel}")
                return
        except Exception:
            continue


def extract_rates_from_text(text: str, lender_id: str, cashback) -> list:
    """
    Extract rate entries from page text using regex.
    Looks for percentage patterns (e.g. 3.25%) and uses surrounding
    context (±5 lines) to determine term, type, LTV, and green status.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rates = []
    seen_rates = set()

    rate_pattern = re.compile(r'\b(\d\.\d{1,2})\s*%')

    for i, line in enumerate(lines):
        match = rate_pattern.search(line)
        if not match:
            continue

        rate_val = float(match.group(1))

        # Sanity check — Irish mortgage rates should be in this range
        if not (1.5 <= rate_val <= 10.0):
            continue

        # Skip APRC/APR lines — we'll derive those
        if re.search(r'\bAPRC?\b|\bAnnual\s+Percentage\b', line, re.I):
            continue

        # Context window — 5 lines either side
        ctx_start = max(0, i - 5)
        ctx_end = min(len(lines), i + 6)
        context = " ".join(lines[ctx_start:ctx_end]).lower()

        # Skip if context suggests this isn't a mortgage rate
        if any(x in context for x in ['savings', 'deposit account', 'personal loan', 'credit card', 'overdraft']):
            continue

        # Determine term
        term = None
        for pattern, years in TERM_PATTERNS:
            if re.search(pattern, context, re.I):
                term = years
                break

        # Determine type
        is_variable = bool(re.search(r'\bvariable\b|\btracker\b|\bsvr\b', context, re.I))
        is_green = bool(re.search(r'\bgreen\b|\bber\s*a\b|\benergy\b|\bsustain', context, re.I))

        if is_variable:
            rate_type = "variable"
            term = None
        else:
            rate_type = "fixed"
            if not term:
                continue  # Can't use a fixed rate without knowing the term

        # Determine LTV
        ltv = 80
        ltv_match = re.search(r'(\d{2})\s*%\s*ltv|ltv\s*(?:of\s*)?(\d{2})\s*%|up\s*to\s*(\d{2})\s*%', context, re.I)
        if ltv_match:
            ltv = int(next(g for g in ltv_match.groups() if g))
        elif '90' in context:
            ltv = 90
        elif '60' in context and 'ltv' in context:
            ltv = 60
        elif '75' in context and 'ltv' in context:
            ltv = 75

        # Deduplicate
        key = (rate_type, term, ltv, is_green, rate_val)
        if key in seen_rates:
            continue
        seen_rates.add(key)

        rate_id = f"{lender_id}-{'g' if is_green else ('v' if is_variable else 'f')}{term or 'v'}-{ltv}"

        rates.append({
            "id": rate_id,
            "type": rate_type,
            "term_years": term,
            "ltv_max": ltv,
            "rate": rate_val,
            "aprc": round(rate_val + 0.07, 2),
            "green": is_green,
            "cashback": cashback,
            "notes": "BER A or B required" if is_green else "",
        })

    return rates


def scrape_lender(page, lender: dict) -> list | None:
    """Visit each URL for a lender, return rates or None."""
    lender_id = lender["id"]
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    for url in lender["urls"]:
        try:
            logger.info(f"[{lender_id}] Trying {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for JS to render
            page.wait_for_timeout(3000)
            dismiss_cookies(page)
            page.wait_for_timeout(1000)

            # Wait a bit more for any lazy-loaded content
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PlaywrightTimeout:
                pass  # networkidle timeout is fine — page may have live requests

            page.wait_for_timeout(1000)

            # Save screenshot for debugging
            screenshot_path = SCREENSHOTS_DIR / f"{lender_id}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            logger.debug(f"[{lender_id}] Screenshot saved to {screenshot_path}")

            # Extract full page text
            text = page.locator("body").inner_text()
            logger.debug(f"[{lender_id}] Page text length: {len(text)} chars")

            if len(text) < 200:
                logger.warning(f"[{lender_id}] Page text too short ({len(text)} chars) — may be blocked or empty")
                continue

            rates = extract_rates_from_text(text, lender_id, lender["cashback"])

            if rates:
                logger.info(f"[{lender_id}] Found {len(rates)} rates at {url}")
                return rates
            else:
                logger.warning(f"[{lender_id}] No rates extracted from {url} — trying next URL")

        except Exception as e:
            logger.error(f"[{lender_id}] Error on {url}: {e}")
            continue

    return None


def load_existing() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"lenders": []}


def merge_rates(data: dict, lender_id: str, new_rates: list) -> dict:
    updated = copy.deepcopy(data)
    for lender in updated.get("lenders", []):
        if lender["id"] == lender_id:
            lender["rates"] = new_rates
            return updated
    logger.warning(f"[{lender_id}] Not found in rates.json — skipping")
    return updated


def write_output(data: dict, dry_run: bool):
    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if dry_run:
        logger.info("DRY RUN — output not written")
        return
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Written to {DATA_FILE}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lender", help="Single lender id to scrape")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger.info("=" * 60)
    logger.info(f"MortgageWatch scraper v2 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    existing = load_existing()
    data = copy.deepcopy(existing)

    lenders_to_run = LENDERS
    if args.lender:
        lenders_to_run = [l for l in LENDERS if l["id"] == args.lender]
        if not lenders_to_run:
            logger.error(f"Unknown lender: {args.lender}")
            sys.exit(1)

    results = {"success": [], "failed": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )

        for lender in lenders_to_run:
            lender_id = lender["id"]
            logger.info(f"── Scraping {lender['name']} ──────────────────")

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="en-IE",
            )
            page = context.new_page()

            try:
                new_rates = scrape_lender(page, lender)
                if new_rates:
                    data = merge_rates(data, lender_id, new_rates)
                    results["success"].append(lender_id)
                else:
                    logger.warning(f"[{lender_id}] No rates found — existing data retained")
                    results["failed"].append(lender_id)
            except Exception as e:
                logger.error(f"[{lender_id}] Unexpected error: {e}", exc_info=True)
                results["failed"].append(lender_id)
            finally:
                context.close()

        browser.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info(f"  ✓ Success: {', '.join(results['success']) or 'none'}")
    logger.info(f"  ✗ Failed : {', '.join(results['failed']) or 'none'}")
    logger.info("=" * 60)

    write_output(data, args.dry_run)

    if len(results["failed"]) == len(lenders_to_run):
        sys.exit(1)


if __name__ == "__main__":
    main()
