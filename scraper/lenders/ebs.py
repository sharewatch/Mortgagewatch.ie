"""
EBS mortgage rate scraper.
Target: https://www.ebs.ie/mortgages/mortgage-rates

EBS is an AIB Group subsidiary. Their rates page is a straightforward
HTML table, usually with fewer products than the main banks.
"""
import logging
import re
from .base import BaseScraper, clean_rate, aprc_from_rate

logger = logging.getLogger(__name__)

URL = "https://www.ebs.ie/mortgages/mortgage-rates"

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


class EBSScraper(BaseScraper):
    lender_id = "ebs"
    lender_name = "EBS"

    def scrape(self):
        try:
            self.page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(2000)

            try:
                self.page.locator("button:has-text('Accept All'), button:has-text('Accept')").first.click(timeout=3000)
                self.page.wait_for_timeout(500)
            except Exception:
                pass

            rates = []
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
                is_variable = "variable" in row_text or "tracker" in row_text
                term = None if is_variable else (parse_term(desc) or parse_term(row_text))
                ltv = 90 if "90" in row_text else 80

                rates.append({
                    "id": f"ebs-{'v' if is_variable else 'f'}{term or 'v'}-{ltv}",
                    "type": "variable" if is_variable else "fixed",
                    "term_years": term,
                    "ltv_max": ltv,
                    "rate": rate_val,
                    "aprc": aprc_val if aprc_val else aprc_from_rate(rate_val),
                    "green": False,
                    "cashback": None,
                    "notes": "FTB eligible" if ltv >= 90 else "",
                })

            if rates:
                self.log_rates(rates)
                return rates

            logger.warning("[ebs] No rates scraped")
            return None

        except Exception as e:
            logger.error(f"[ebs] Scrape failed: {e}")
            return None
