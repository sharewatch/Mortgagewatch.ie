"""
Permanent TSB mortgage rate scraper.
Target: https://www.permanenttsb.ie/mortgages/our-rates/

PTSB publishes rates in tab-based sections (Fixed, Variable, Green).
Rates include €2,000 cashback on most products.
"""
import logging
import re
from .base import BaseScraper, clean_rate, aprc_from_rate

logger = logging.getLogger(__name__)

URL = "https://www.permanenttsb.ie/mortgages/our-rates/"

TERM_MAP = {
    "1 year": 1, "1-year": 1,
    "2 year": 2, "2-year": 2,
    "3 year": 3, "3-year": 3,
    "5 year": 5, "5-year": 5,
    "7 year": 7, "7-year": 7,
    "10 year": 10, "10-year": 10,
}


def parse_term(text: str):
    text_lower = text.lower()
    for key, val in TERM_MAP.items():
        if key in text_lower:
            return val
    return None


def parse_ltv(text: str):
    match = re.search(r'(\d+)\s*%', text)
    if match:
        return int(match.group(1))
    return 80


class PTSBScraper(BaseScraper):
    lender_id = "ptsb"
    lender_name = "PTSB"

    def scrape(self):
        try:
            self.page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(2500)

            # Accept cookies
            try:
                self.page.locator("button:has-text('Accept All')").first.click(timeout=3000)
                self.page.wait_for_timeout(500)
            except Exception:
                pass

            rates = []

            # PTSB uses tab panels — click each tab to expose rates
            tabs = ["Fixed", "Variable", "Green"]
            for tab_label in tabs:
                try:
                    tab = self.page.locator(f"button:has-text('{tab_label}'), [role='tab']:has-text('{tab_label}')").first
                    tab.click(timeout=3000)
                    self.page.wait_for_timeout(800)
                except Exception:
                    pass  # Tab may not exist or already active

                is_green = tab_label == "Green"
                is_variable = tab_label == "Variable"

                rows = self.page.locator("table tr").all()
                for row in rows:
                    cells = [td.inner_text().strip() for td in row.locator("td, th").all()]
                    if len(cells) < 3:
                        continue

                    row_text = " ".join(cells).lower()
                    rate_val = None
                    aprc_val = None

                    for cell in cells:
                        r = clean_rate(cell)
                        if r and rate_val is None:
                            rate_val = r
                        elif r and aprc_val is None:
                            aprc_val = r

                    if not rate_val:
                        continue

                    desc = cells[0]
                    term = None if is_variable else (parse_term(desc) or parse_term(row_text))
                    ltv = 80

                    for cell in cells:
                        if "%" in cell and ("up to" in cell.lower() or "ltv" in cell.lower() or "90" in cell):
                            ltv = parse_ltv(cell)
                            break

                    # Check for cashback mention in row
                    cashback = 2000 if "cashback" in row_text or "cash back" in row_text else 2000  # PTSB standard

                    rates.append({
                        "id": f"ptsb-{'g' if is_green else ('v' if is_variable else 'f')}{term or 'v'}-{ltv}",
                        "type": "variable" if is_variable else "fixed",
                        "term_years": term,
                        "ltv_max": ltv,
                        "rate": rate_val,
                        "aprc": aprc_val if aprc_val else aprc_from_rate(rate_val),
                        "green": is_green,
                        "cashback": cashback,
                        "notes": "BER A or B required" if is_green else ("FTB up to 90% LTV" if ltv >= 90 else ""),
                    })

            if rates:
                # Deduplicate by id, keeping first occurrence
                seen = set()
                deduped = []
                for r in rates:
                    if r["id"] not in seen:
                        seen.add(r["id"])
                        deduped.append(r)
                self.log_rates(deduped)
                return deduped

            logger.warning("[ptsb] No rates scraped")
            return None

        except Exception as e:
            logger.error(f"[ptsb] Scrape failed: {e}")
            return None
