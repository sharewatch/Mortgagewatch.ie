"""
Finance Ireland mortgage rate scraper.
Target: https://www.financeireland.ie/products/residential-mortgages/overview/

Finance Ireland is a broker-only non-bank lender.
Their rates may be embedded in the page or require navigating to a rates sub-page.
"""
import logging
import re
from .base import BaseScraper, clean_rate, aprc_from_rate

logger = logging.getLogger(__name__)

URL = "https://www.financeireland.ie/products/residential-mortgages/overview/"
RATES_URL = "https://www.financeireland.ie/products/residential-mortgages/rates/"

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


class FinanceIrelandScraper(BaseScraper):
    lender_id = "finance-ireland"
    lender_name = "Finance Ireland"

    def scrape(self):
        # Try rates sub-page first, fall back to overview
        for url in [RATES_URL, URL]:
            result = self._try_url(url)
            if result:
                return result
        logger.warning("[finance-ireland] No rates found on any page")
        return None

    def _try_url(self, url: str):
        try:
            self.page.goto(url, wait_until="networkidle", timeout=40000)
            self.page.wait_for_timeout(3000)

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
                if len(cells) <= 2 and "green" not in row_text:
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
                ltv = parse_ltv(row_text) or 80

                rates.append({
                    "id": f"fi-{'g' if current_is_green else 'f'}{term or 'f'}-{ltv}",
                    "type": "fixed",
                    "term_years": term,
                    "ltv_max": ltv,
                    "rate": rate_val,
                    "aprc": aprc_val if aprc_val else aprc_from_rate(rate_val),
                    "green": current_is_green,
                    "cashback": None,
                    "notes": "BER A or B required" if current_is_green else "",
                })

            return rates if rates else None

        except Exception as e:
            logger.error(f"[finance-ireland] Failed on {url}: {e}")
            return None
