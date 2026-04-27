"""
Bank of Ireland mortgage rate scraper.
Target: https://www.bankofireland.com/mortgages/mortgage-rates/

BOI publishes rates in structured HTML tables. They typically include:
  - Product name / term
  - LTV band
  - Interest rate
  - APRC
  - Cashback (€2,000 on most products)
"""
import logging
import re
from .base import BaseScraper, clean_rate, aprc_from_rate

logger = logging.getLogger(__name__)

URL = "https://www.bankofireland.com/mortgages/mortgage-rates/"

TERM_MAP = {
    "1 year": 1, "1-year": 1,
    "2 year": 2, "2-year": 2,
    "3 year": 3, "3-year": 3,
    "4 year": 4, "4-year": 4,
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


class BOIScraper(BaseScraper):
    lender_id = "boi"
    lender_name = "Bank of Ireland"

    def scrape(self):
        try:
            self.page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(2500)

            # Accept cookies if banner present
            try:
                self.page.locator("button:has-text('Accept')").first.click(timeout=3000)
                self.page.wait_for_timeout(500)
            except Exception:
                pass

            rates = []
            rows = self.page.locator("table tr").all()
            current_is_green = False

            for row in rows:
                cells = [td.inner_text().strip() for td in row.locator("td, th").all()]
                if not cells:
                    continue

                row_text = " ".join(cells).lower()

                # Detect green section
                if "green" in row_text and len(cells) <= 2:
                    current_is_green = True
                    continue
                if ("fixed" in row_text or "variable" in row_text) and len(cells) <= 2:
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
                ltv = 80

                for cell in cells:
                    if "%" in cell and ("up to" in cell.lower() or "ltv" in cell.lower()):
                        ltv = parse_ltv(cell)
                        break

                is_variable = "variable" in row_text or "tracker" in row_text

                rates.append({
                    "id": f"boi-{'g' if current_is_green else ('v' if is_variable else 'f')}{term or 'v'}-{ltv}",
                    "type": "variable" if is_variable else "fixed",
                    "term_years": None if is_variable else term,
                    "ltv_max": ltv,
                    "rate": rate_val,
                    "aprc": aprc_val if aprc_val else aprc_from_rate(rate_val),
                    "green": current_is_green,
                    "cashback": 2000,  # BOI standard cashback
                    "notes": "BER A or B required" if current_is_green else "",
                })

            if rates:
                self.log_rates(rates)
                return rates

            logger.warning("[boi] Table parse returned no rates")
            return None

        except Exception as e:
            logger.error(f"[boi] Scrape failed: {e}")
            return None
