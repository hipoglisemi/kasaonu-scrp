import requests
from bs4 import BeautifulSoup
import re
import urllib3
import concurrent.futures

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from src.database import get_db_session
from src.models import Campaign

def check_url(c_id, url, title):
    try:
        resp = requests.get(url, timeout=10, verify=False, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            
            # Simple regex to find dates like "30 Haziran", "Temmuz", "31 Temmuz 2026"
            matches = re.findall(r'\b(?:1[0-9]|2[0-9]|3[01]|0?[1-9])\s*(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\b', text, re.IGNORECASE)
            
            # Get unique matches
            unique_matches = list(set([m.lower() for m in matches]))
            
            return f"ID: {c_id} | Title: {title[:30]}... | Found Dates: {unique_matches}"
        else:
            return f"ID: {c_id} | HTTP {resp.status_code}"
    except Exception as e:
        return f"ID: {c_id} | Error: {str(e)[:30]}"

def main():
    with open("extended_ids.txt", "r") as f:
        ids = [int(line.strip()) for line in f if line.strip()]
        
    with get_db_session() as db:
        camps = db.query(Campaign).filter(Campaign.id.in_(ids)).all()
        
    print(f"Testing {len(camps)} URLs...")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_url, c.id, c.tracking_url, c.title): c for c in camps if c.tracking_url}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    with open("url_dates_report.txt", "w") as f:
        for r in results:
            f.write(r + "\n")
    print("Done. Report saved to url_dates_report.txt")

if __name__ == "__main__":
    main()
