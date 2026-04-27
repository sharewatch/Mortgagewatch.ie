from .aib import AIBScraper
from .boi import BOIScraper
from .ptsb import PTSBScraper
from .avant import AvantScraper
from .haven import HavenScraper
from .ebs import EBSScraper
from .ics import ICSScraper
from .finance_ireland import FinanceIrelandScraper

ALL_SCRAPERS = [
    AIBScraper,
    BOIScraper,
    PTSBScraper,
    AvantScraper,
    HavenScraper,
    EBSScraper,
    ICSScraper,
    FinanceIrelandScraper,
]
