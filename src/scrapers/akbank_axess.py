


import sys
import os
# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.scrapers.akbank_base import AkbankBaseScraper  # type: ignore # pyre-ignore[21]
except ImportError:
    from akbank_base import AkbankBaseScraper  # type: ignore # pyre-ignore[21]

class AkbankAxessScraper(AkbankBaseScraper):
    """
    Scraper for Akbank Axess campaigns.
    """
    def __init__(self):
        AkbankBaseScraper.__init__(
            self,
            card_name="Axess",
            base_url="https://www.axess.com.tr",
            list_url="https://www.axess.com.tr/ajax/kampanya-ajax.aspx",
            referer_url="https://www.axess.com.tr/axess/kampanya/8/393/kampanyalar",
            list_params={'checkBox': '[0]', 'searchWord': '""'}  # type: ignore # pyre-ignore[16,6]
        )

if __name__ == "__main__":
    scraper = AkbankAxessScraper()
    scraper.run()
