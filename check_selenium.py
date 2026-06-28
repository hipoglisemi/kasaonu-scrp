import time
import re
import concurrent.futures
from src.database import get_db_session
from src.models import Campaign

def check_with_selenium(c):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from bs4 import BeautifulSoup
    
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        driver.get(c.tracking_url)
        time.sleep(3) # Wait for JS to render
        html = driver.page_source
        driver.quit()
        
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ', strip=True).lower()
        
        has_haziran = "30 haziran" in text or "haziran sonuna" in text or "haziran sonu" in text
        has_temmuz = "temmuz" in text
        
        # Look for explicit "tarihleri arasında", "geçerlidir" near dates
        date_matches = re.findall(r'\b(?:1[0-9]|2[0-9]|3[01]|0?[1-9])\s*(?:ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)\b', text)
        
        status = "TARİHSİZ (SÜRESİZ)"
        if has_haziran and not has_temmuz:
            status = "30 HAZİRAN BULUNDU!"
        elif has_temmuz:
            status = "TEMMUZ BULUNDU!"
        elif date_matches:
            status = f"FARKLI TARİH: {list(set(date_matches))}"
            
        return f"ID: {c.id} | {c.title[:30]} | {status}"
    except Exception as e:
        return f"ID: {c.id} | ERROR: {str(e)[:30]}"

def main():
    with open("belirsiz_ids.txt", "r") as f:
        content = f.read().strip()
        if not content:
            print("No IDs found")
            return
        ids = [int(x) for x in content.split()]
        
    with get_db_session() as db:
        camps = db.query(Campaign).filter(Campaign.id.in_(ids)).all()
        
    print(f"Checking {len(camps)} campaigns with Selenium...")
    
    results = []
    # Run a bit slower to avoid crashing Selenium
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(check_with_selenium, c): c for c in camps}
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            res = future.result()
            results.append(res)
            print(f"[{i+1}/{len(camps)}] {res}")
            
    with open("selenium_results.txt", "w") as f:
        for r in results:
            f.write(r + "\n")
            
if __name__ == "__main__":
    main()
