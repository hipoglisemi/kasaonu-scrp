import os
import sys
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Path setup
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def test_yapikredi_extraction(url):
    print(f"\n--- Testing Yapı Kredi Extraction ---")
    print(f"URL: {url}")
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        response.raise_for_status()
        full_html = response.text
        soup = BeautifulSoup(full_html, 'html.parser')
        main_content_div = soup.select_one('.campaign-detail-content, .campaign-detail, main')
        content = str(main_content_div) if main_content_div else full_html
        clean_text = BeautifulSoup(content, 'html.parser').get_text(separator=' ', strip=True)
        print(f"✅ Extracted Clean Text Length: {len(clean_text)}")
        print(f"Snippet: {clean_text[:200]}...")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_garanti_extraction(url):
    print(f"\n--- Testing Garanti Extraction ---")
    print(f"URL: {url}")
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        content_parts = []
        info_boxes = soup.select('.campaign-detail__info, .campaign-detail__others, .info-content')
        for box in info_boxes:
            content_parts.append(box.get_text(separator='\n'))
        
        detail_selectors = ['.how-to-win', '.campaign-detail__content', '.campaign-detail-tab-content', '.campaign-description', '#tab-details']
        for selector in detail_selectors:
            elements = soup.select(selector)
            for el in elements:
                text = el.get_text(separator='\n', strip=True)
                if text and text not in content_parts:
                    content_parts.append(text)
        
        content_text = '\n\n'.join(content_parts)
        print(f"✅ Extracted Clean Text Length: {len(content_text)}")
        print(f"Snippet: {content_text[:200]}...")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    # Test URLs from the audit
    test_yapikredi_extraction("https://www.worldcard.com.tr/kampanyalar/worlde-ozel-opet-istasyonlarinda-chippin-uygulamasi-uzerinden-1300-tl-ve-uzeri-harcamaya-nisan-2026")
    test_garanti_extraction("https://www.bonus.com.tr/kampanyalar/bonus-platinum-restoran-kampanyalari")
