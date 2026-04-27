"""
Haven Mortgages rate scraper.
Target: https://www.havenmortgages.ie/mortgage-rates/

Haven is an AIB Group subsidiary, broker-only.
Rates page is typically a simple HTML table.
"""
import logging
import re
from .base import BaseScraper, clean_rate, aprc_from_rate

logger = logging.getLogger(__name__)

URL = "https://www.havenmortgages.ie/mortgage-rates/"

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


class HavenScraper(BaseScraper):
    lender_id = "haven"
    lender_name = "Haven Mortgages"

    def scrape(self):
        try:
            self.page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(2000)

            try:
                self.page.locator("button:has-text('Accept')").first.click(timeout=3000)
                self.page.wait_for_timeout(500)
            except Exception:
                pass

            rates = []
            current_is_green = False
            rows = self.page.locator("table tr").all()

            for row in rows:
                cells = [td.inner_text().strip() for td in row.locator("td, th").all()]
                if not cells:
                    continue

                row_text = " ".join(cells).lower()

                if "green" in row_text and len(cells) <= 2:
                    current_is_green = True
                    continue
                if len(cells) <= 2 and "green" not in row_text and any(x in row_text for x in ["fixed", "variable", "rate"]):
                    current_is_green = False
                    continue

                if len(cells) < 3:
                    continue

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
                term = parse_term(desc) or parse_term(row_text)
                is_variable = "variable" in row_text
                ltv = 80

                for cell in cells:
                    if "%" in cell and any(x in cell for x in ["60", "70", "75", "80", "90"]):
                        ltv = parse_ltv(cell)
                        break

                rates.append({
                    "id": f"hvn-{'g' if current_is_green else ('v' if is_variable else 'f')}{term or 'v'}-{ltv}",
                    "type": "variable" if is_variable else "fixed",
                    "term_years": None if is_variable else term,
                    "ltv_max": ltv,
                    "rate": rate_val,
                    "aprc": aprc_val if aprc_val else aprc_from_rate(rate_val),
                    "green": current_is_green,
                    "cashback": None,
                    "notes": "BER A or B" if current_is_green else "",
                })

            if rates:
                self.log_rates(rates)
                return rates

            logger.warning("[haven] No rates scraped")
            return None

        except Exception as e:
            logger.error(f"[haven] Scrape failed: {e}")
            return None
