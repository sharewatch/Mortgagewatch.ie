"""
MortgageWatch.ie — Daily Rate Scraper
======================================
Runs all lender scrapers, merges results with existing rates.json,
writes updated rates.json to /data/rates.json.

Usage:
  python scrape.py                  # scrape all lenders
  python scrape.py --lender aib     # scrape one lender only
  python scrape.py --dry-run        # scrape but don't write output
  python scrape.py --verbose        # debug logging
"""

import argparse
import json
import logging
import sys
import copy
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

from lenders import ALL_SCRAPERS

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data" / "rates.json"
LOG_FILE = REPO_ROOT / "scraper" / "scrape.log"

# ── Logging ────────────────────────────────────────────────────────────────
def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )

logger = logging.getLogger(__name__)


# ── Load existing data ──────────────────────────────────────────────────────
def load_existing() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    logger.warning("No existing rates.json found — starting fresh")
    return {"lenders": []}


# ── Merge scraped rates into existing lender record ─────────────────────────
def merge_rates(existing: dict, lender_id: str, new_rates: list) -> dict:
    """
    Replace the rates array for a given lender while preserving all other
    lender metadata (name, color, about, pros, cons, urls etc.)
    """
    updated = copy.deepcopy(existing)
    for lender in updated.get("lenders", []):
        if lender["id"] == lender_id:
            old_count = len(lender.get("rates", []))
            lender["rates"] = new_rates
            logger.info(f"[{lender_id}] Rates updated: {old_count} → {len(new_rates)}")
            return updated
    logger.warning(f"[{lender_id}] Lender not found in rates.json — skipping merge")
    return updated


# ── Rate change detection ───────────────────────────────────────────────────
def detect_changes(existing: dict, lender_id: str, new_rates: list) -> list:
    """Return list of human-readable change strings for logging."""
    changes = []
    old_rates = {}
    for lender in existing.get("lenders", []):
        if lender["id"] == lender_id:
            for r in lender.get("rates", []):
                old_rates[r["id"]] = r["rate"]
            break

    for r in new_rates:
        rid = r["id"]
        new_rate = r["rate"]
        if rid in old_rates:
            old_rate = old_rates[rid]
            if old_rate != new_rate:
                direction = "↓" if new_rate < old_rate else "↑"
                changes.append(f"  {direction} {rid}: {old_rate}% → {new_rate}%")
        else:
            changes.append(f"  + NEW {rid}: {new_rate}%")

    removed = [rid for rid in old_rates if rid not in {r["id"] for r in new_rates}]
    for rid in removed:
        changes.append(f"  - REMOVED {rid}")

    return changes


# ── Write output ────────────────────────────────────────────────────────────
def write_output(data: dict, dry_run: bool):
    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if dry_run:
        logger.info("DRY RUN — output not written")
        print(json.dumps(data, indent=2))
        return
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Written to {DATA_FILE}")


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MortgageWatch rate scraper")
    parser.add_argument("--lender", help="Scrape a single lender by id (e.g. aib)")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but don't write output")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger.info("=" * 60)
    logger.info(f"MortgageWatch scraper starting — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    existing = load_existing()
    data = copy.deepcopy(existing)

    scrapers_to_run = ALL_SCRAPERS
    if args.lender:
        scrapers_to_run = [s for s in ALL_SCRAPERS if s.lender_id == args.lender]
        if not scrapers_to_run:
            logger.error(f"Unknown lender: {args.lender}")
            sys.exit(1)

    results = {"success": [], "failed": [], "unchanged": []}

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

        for ScraperClass in scrapers_to_run:
            lender_id = ScraperClass.lender_id
            lender_name = ScraperClass.lender_name
            logger.info(f"── Scraping {lender_name} ──────────────────────────")

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-IE",
            )
            page = context.new_page()

            try:
                scraper = ScraperClass(page)
                new_rates = scraper.scrape()

                if new_rates and len(new_rates) > 0:
                    # Detect and log changes
                    changes = detect_changes(existing, lender_id, new_rates)
                    if changes:
                        logger.info(f"[{lender_id}] Rate changes detected:")
                        for c in changes:
                            logger.info(c)
                    else:
                        logger.info(f"[{lender_id}] No rate changes")
                        results["unchanged"].append(lender_id)

                    data = merge_rates(data, lender_id, new_rates)
                    results["success"].append(lender_id)
                else:
                    logger.warning(
                        f"[{lender_id}] Scrape returned no rates — "
                        f"keeping existing data. Manual review may be needed."
                    )
                    results["failed"].append(lender_id)

            except Exception as e:
                logger.error(f"[{lender_id}] Unexpected error: {e}", exc_info=True)
                results["failed"].append(lender_id)
            finally:
                context.close()

        browser.close()

    # ── Summary ──
    logger.info("")
    logger.info("=" * 60)
    logger.info("SCRAPE SUMMARY")
    logger.info(f"  ✓ Success : {', '.join(results['success']) or 'none'}")
    logger.info(f"  ~ Unchanged: {', '.join(results['unchanged']) or 'none'}")
    logger.info(f"  ✗ Failed  : {', '.join(results['failed']) or 'none'}")
    logger.info("=" * 60)

    if results["failed"]:
        logger.warning(
            f"{len(results['failed'])} lender(s) failed to scrape. "
            "Existing rates retained. Check scrape.log for details."
        )

    write_output(data, args.dry_run)

    # Exit with error code if ALL scrapers failed (useful for GitHub Actions alerting)
    if len(results["failed"]) == len(scrapers_to_run):
        sys.exit(1)


if __name__ == "__main__":
    main()
