"""
Base scraper class. Every lender scraper inherits from this.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def clean_rate(text: str) -> Optional[float]:
    """Extract a float percentage from a string like '3.25%' or '3.25 %' or '3.25'."""
    if not text:
        return None
    text = text.strip().replace('%', '').replace(',', '.').strip()
    match = re.search(r'\d+\.\d+', text)
    if match:
        val = float(match.group())
        if 1.0 <= val <= 15.0:   # sanity check — mortgage rates should be in this range
            return round(val, 2)
    return None


def aprc_from_rate(rate: float, margin: float = 0.07) -> float:
    """Estimate APRC from nominal rate. Used as fallback when APRC not scraped directly."""
    return round(rate + margin, 2)


class BaseScraper:
    lender_id: str = ""
    lender_name: str = ""

    def __init__(self, page):
        self.page = page

    def scrape(self) -> Optional[list]:
        """
        Override in each lender subclass.
        Should return a list of rate dicts matching the rates.json schema, or None on failure.
        """
        raise NotImplementedError

    def safe_text(self, selector: str, timeout: int = 5000) -> Optional[str]:
        """Return stripped inner text of first matching element, or None."""
        try:
            el = self.page.locator(selector).first
            el.wait_for(timeout=timeout)
            return el.inner_text().strip()
        except Exception:
            return None

    def all_text(self, selector: str) -> list:
        """Return list of stripped inner texts for all matching elements."""
        try:
            return [el.inner_text().strip() for el in self.page.locator(selector).all()]
        except Exception:
            return []

    def log_rates(self, rates: list):
        logger.info(f"[{self.lender_id}] Scraped {len(rates)} rates")
        for r in rates:
            logger.debug(f"  {r.get('type')} {r.get('term_years')}yr {r.get('ltv_max')}% LTV → {r.get('rate')}%")
