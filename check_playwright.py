import time
import re
import concurrent.futures
from src.database import get_db_session
from src.models import Campaign

def check_with_playwright(c):
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                ignore_https_errors=True
            )
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            try:
                page.goto(c.tracking_url, timeout=30000, wait_until='domcontentloaded')
                page.wait_for_timeout(3000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                page.wait_for_timeout(1000)
            except Exception as e:
                pass
                
            html = page.content()
            browser.close()
            
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ', strip=True).lower()
        
        has_haziran = "30 haziran" in text or "haziran sonuna" in text or "haziran sonu" in text
        has_temmuz = "temmuz" in text
        has_agustos = "ağustos" in text
        
        date_matches = re.findall(r'\b(?:1[0-9]|2[0-9]|3[01]|0?[1-9])\s*(?:ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)\b', text)
        
        status = "TARİHSİZ (SÜRESİZ)"
        if has_haziran and not has_temmuz and not has_agustos:
            status = "❌ 30 HAZİRAN BULUNDU!"
        elif has_temmuz:
            status = "✅ TEMMUZ BULUNDU!"
        elif date_matches:
            status = f"❓ FARKLI TARİH: {list(set(date_matches))}"
            
        return f"ID: {c.id} | {c.title[:30]}... | {status} | Uzunluk: {len(text)}"
    except Exception as e:
        return f"ID: {c.id} | ERROR: {str(e)[:30]}"

def main():
    fixed_ids = [10382, 16182, 10379]
    with open("belirsiz_ids.txt", "r") as f:
        content = f.read().strip()
        if not content:
            print("No IDs found")
            return
        ids = [int(x) for x in content.split() if int(x) not in fixed_ids]
        
    with get_db_session() as db:
        camps = db.query(Campaign).filter(Campaign.id.in_(ids)).all()
        
    print(f"Checking {len(camps)} campaigns with Playwright...")
    
    results = []
    # Use max_workers=3 for Playwright to avoid memory issues/crashes
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(check_with_playwright, c): c for c in camps}
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            res = future.result()
            results.append(res)
            print(f"[{i+1}/{len(camps)}] {res}")
            
    with open("playwright_results.txt", "w") as f:
        # Sort by HAZIRAN first, then others
        results.sort(key=lambda x: ("HAZİRAN" in x, "TEMMUZ" in x, x), reverse=True)
        for r in results:
            f.write(r + "\n")
            
if __name__ == "__main__":
    main()
