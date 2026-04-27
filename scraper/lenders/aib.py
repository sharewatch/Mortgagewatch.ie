"""
AIB mortgage rate scraper.
Target: https://aib.ie/mortgages/mortgage-rates

AIB publishes a structured rate table. Rows typically contain:
  - Product description (e.g. "3 Year Fixed Rate")
  - LTV band (e.g. "Up to 80%")
  - Interest rate (e.g. "3.65%")
  - APRC (e.g. "3.72%")

Green mortgage rates are listed in a separate section labelled "Green Mortgage".
"""
import logging
import re
from .base import BaseScraper, clean_rate, aprc_from_rate

logger = logging.getLogger(__name__)

URL = "https://aib.ie/mortgages/mortgage-rates"

TERM_MAP = {
    "1 year": 1, "1-year": 1, "one year": 1,
    "2 year": 2, "2-year": 2, "two year": 2,
    "3 year": 3, "3-year": 3, "three year": 3,
    "4 year": 4, "4-year": 4, "four year": 4,
    "5 year": 5, "5-year": 5, "five year": 5,
    "7 year": 7, "7-year": 7, "seven year": 7,
    "10 year": 10, "10-year": 10, "ten year": 10,
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
    if "60" in text:
        return 60
    if "80" in text:
        return 80
    if "90" in text:
        return 90
    return 80  # default


class AIBScraper(BaseScraper):
    lender_id = "aib"
    lender_name = "AIB"

    def scrape(self):
        try:
            self.page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(2000)

            rates = []

            # AIB renders rates in tables. We grab all table rows and parse them.
            rows = self.page.locator("table tr").all()

            current_is_green = False
            rate_id_counter = 1

            for row in rows:
                cells = [td.inner_text().strip() for td in row.locator("td, th").all()]
                if not cells:
                    continue

                # Detect green mortgage section heading
                row_text = " ".join(cells).lower()
                if "green" in row_text and len(cells) <= 2:
                    current_is_green = True
                    continue
                if "standard" in row_text and "fixed" in row_text and len(cells) <= 2:
                    current_is_green = False
                    continue

                # Need at least 3 cells: description, rate, aprc (LTV may be combined)
                if len(cells) < 3:
                    continue

                # Try to find a rate cell (contains %)
                rate_val = None
                aprc_val = None
                desc = ""
                ltv = 80

                for i, cell in enumerate(cells):
                    r = clean_rate(cell)
                    if r and rate_val is None:
                        rate_val = r
                    elif r and aprc_val is None:
                        aprc_val = r

                if not rate_val:
                    continue

                # Description is typically first cell
                desc = cells[0]
                term = parse_term(desc)

                # LTV — look for a cell containing %
                for cell in cells:
                    if "up to" in cell.lower() or "ltv" in cell.lower():
                        ltv = parse_ltv(cell)
                        break

                # Determine type
                if "variable" in desc.lower():
                    rate_type = "variable"
                    term = None
                elif "tracker" in desc.lower():
                    rate_type = "variable"
                    term = None
                else:
                    rate_type = "fixed"

                rate_entry = {
                    "id": f"aib-{'g' if current_is_green else 'f'}{term or 'v'}-{ltv}",
                    "type": rate_type if not current_is_green else "fixed",
                    "term_years": term,
                    "ltv_max": ltv,
                    "rate": rate_val,
                    "aprc": aprc_val if aprc_val else aprc_from_rate(rate_val),
                    "green": current_is_green,
                    "cashback": None,
                    "notes": "BER A or B required" if current_is_green else "",
                }

                rates.append(rate_entry)
                rate_id_counter += 1

            if rates:
                self.log_rates(rates)
                return rates

            logger.warning(f"[aib] Table parse returned no rates — trying fallback text parse")
            return self._fallback_parse()

        except Exception as e:
            logger.error(f"[aib] Scrape failed: {e}")
            return None

    def _fallback_parse(self):
        """
        Fallback: extract all percentage figures from page text and try to
        reconstruct rate entries. Less reliable but better than nothing.
        """
        try:
            body = self.page.locator("body").inner_text()
            lines = [l.strip() for l in body.splitlines() if l.strip()]
            rates = []
            for i, line in enumerate(lines):
                rate = clean_rate(line)
                if not rate:
                    continue
                context = " ".join(lines[max(0, i-3):i+2]).lower()
                term = parse_term(context)
                if not term and "variable" not in context:
                    continue
                rates.append({
                    "id": f"aib-fallback-{len(rates)+1}",
                    "type": "variable" if "variable" in context else "fixed",
                    "term_years": term,
                    "ltv_max": parse_ltv(context) or 80,
                    "rate": rate,
                    "aprc": aprc_from_rate(rate),
                    "green": "green" in context,
                    "cashback": None,
                    "notes": "Fallback parse — verify manually",
                })
            return rates if rates else None
        except Exception as e:
            logger.error(f"[aib] Fallback parse failed: {e}")
            return None
