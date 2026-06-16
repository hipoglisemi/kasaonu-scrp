



import requests  # type: ignore # pyre-ignore[21]
import time  # type: ignore # pyre-ignore[21]
from typing import List, Optional  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
import sys
import os
# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.scrapers.akbank_base import AkbankBaseScraper  # type: ignore # pyre-ignore[21]

class AkbankWingsScraper(AkbankBaseScraper):
    """
    Scraper for Akbank Wings campaigns.
    Uses the Wings-specific JSON API for discovery.
    """
    
    WINGS_API_URL = "https://www.wingscard.com.tr/api/campaign/list"
    WINGS_BASE_URL = "https://www.wingscard.com.tr"
    
    def __init__(self):
        AkbankBaseScraper.__init__(
            self,
            card_name="Wings",
            base_url=self.WINGS_BASE_URL,
            list_url=self.WINGS_API_URL,
            referer_url="https://www.wingscard.com.tr/kampanyalar"
        )

    def _fetch_campaign_list(self) -> List[str]:  # type: ignore # pyre-ignore[16,6]
        """Fetch all campaign URLs from the Wings JSON API."""
        print(f"📥 Fetching Wings campaign list from API...")
        campaign_urls = []
        
        try:
            # First request to get total page count
            response = self.session.get(self.WINGS_API_URL, params={'page': 1}, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            # Wings API response structure check
            # data.get('data', {}).get('totalCount') or data.get('pageCount')
            data_obj = data.get('data', {})
            page_count = data.get('pageCount') or (data_obj.get('totalCount', 0) // 8 + 1)
            print(f"   Total pages to scan: {page_count}")
            
            for page in range(1, page_count + 1):
                print(f"   Fetching page {page}/{page_count}...")
                
                response = self.session.get(self.WINGS_API_URL, params={'page': page}, timeout=20)
                response.raise_for_status()
                json_response = response.json()
                
                current_data = json_response.get('data', {})
                campaigns = current_data.get('list', [])
                
                if not campaigns:
                    break

                for campaign in campaigns:
                    url_path = campaign.get('url')
                    if url_path:
                        full_url = urljoin(self.WINGS_BASE_URL, url_path)
                        if full_url not in campaign_urls:
                            campaign_urls.append(full_url)
                
                time.sleep(0.5)
                
        except Exception as e:
            print(f"❌ Error fetching Wings campaign API: {e}")
            
        print(f"✅ Found {len(campaign_urls)} campaigns for {self.card_name}")
        return campaign_urls  # type: ignore # pyre-ignore[7]

    def _process_campaign(self, url: str, force: bool = False) -> str:
        """Override to use Wings-specific selectors and Angular state extraction."""
        from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
        from src.services.ai_parser import parse_api_campaign  # type: ignore # pyre-ignore[21]
        import json
        import html
        import re
        
        try:
            print(f"🔍 Processing: {url}")
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            title = None
            image_url = None
            details_text = ""
            
            # 1. Try to extract from Angular SSR State JSON
            script = soup.find('script', type='application/json')
            if script:
                try:
                    content = script.string or ''
                    # Replace encoded quotes and other chars
                    content_clean = content.replace('&q;', '\"').replace('&s;', '\'').replace('&a;', '&')
                    data = json.loads(content_clean)
                    for k, v in data.items():
                        if 'api/page' in k:
                            body = v.get('body', {})
                            data_list = body.get('data', [])
                            for comp in data_list:
                                if comp.get('componentname') == 'campaign_detail':
                                    comp_data = comp.get('data', {})
                                    title = comp_data.get('title')
                                    image_url = comp_data.get('banner_image')
                                    
                                    banner_spot = comp_data.get('banner_spot') or ''
                                    detail_content = comp_data.get('detail_content') or ''
                                    
                                    def clean_html(text):
                                        if not text:
                                            return ''
                                        text = text.replace('&l;', '<').replace('&g;', '>')
                                        text = html.unescape(text)
                                        return BeautifulSoup(text, 'html.parser').get_text(separator='\n', strip=True)
                                        
                                    details_text = clean_html(banner_spot) + '\n' + clean_html(detail_content)
                                    print(f"   ✨ Successfully extracted data from Angular SSR state JSON")
                                    break
                except Exception as json_err:
                    print(f"   ⚠️ SSR State JSON parsing failed: {json_err}")
            
            # 2. Fallbacks if SSR extraction was incomplete or failed
            if not title:
                title_elm = soup.select_one('h1.banner-title')
                if not title_elm:
                    title_elm = soup.select_one('h2.pageTitle')
                title = title_elm.get_text(strip=True) if title_elm else "Kampanya"
                
            if not image_url:
                img_elm = soup.select_one('.privileges-detail-image img')
                if img_elm:
                    image_url = urljoin(self.WINGS_BASE_URL, img_elm.get('src', ''))
                else:
                    banner = soup.select_one('.privileges-detail-banner')
                    if banner and 'style' in banner.attrs:
                        match = re.search(r'url\(["\']?(.*?)["\']?\)', banner['style'])
                        if match:
                            image_url = urljoin(self.WINGS_BASE_URL, match.group(1))
                            
            if not details_text:
                details_container = soup.select_one('.privileges-detail-content') or soup.select_one('.cmsContent')
                details_text = details_container.get_text(separator='\n', strip=True) if details_container else title
                
            # AI Parsing
            ai_data = parse_api_campaign(
                title=title,
                short_description=title,
                content_html=details_text,
                bank_name="Akbank",
                scraper_sector=None,
                tracking_url=url, # Add tracking_url for cache
                force=force
            )
            
            # Save to DB
            return self._save_campaign(title, image_url, ai_data, url)
            
        except Exception as e:
            print(f"❌ Failed to process {url}: {e}")
            return "error"  # type: ignore # pyre-ignore[7]

if __name__ == "__main__":
    scraper = AkbankWingsScraper()
    scraper.run()
