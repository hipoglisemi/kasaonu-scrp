import requests
from bs4 import BeautifulSoup
import re
import urllib3
import concurrent.futures

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from src.database import get_db_session
from src.models import Campaign

def check_url_and_classify(c):
    try:
        resp = requests.get(c.tracking_url or "", timeout=10, verify=False, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            text = soup.get_text(separator=' ', strip=True).lower()
            
            # Simple regex to find "30 haziran" or "temmuz" or "ağustos"
            has_haziran = "30 haziran" in text or "haziran sonuna" in text or "haziran sonu" in text
            has_temmuz = "temmuz" in text
            
            status = "UNKNOWN"
            reason = ""
            
            # If the DB says it's extended to July 31, but the page clearly only talks about June 30
            if c.end_date and c.end_date.month == 7:
                if has_haziran and not has_temmuz:
                    status = "❌ HATALI UZATILMIŞ"
                    reason = "Sayfada 30 Haziran yazıyor ama 31 Temmuz'a uzatılmış."
                elif has_temmuz:
                    status = "✅ DOĞRU UZATILMIŞ"
                    reason = "Sayfada Temmuz tarihi doğrulandı."
                else:
                    status = "❓ BELİRSİZ"
                    reason = "Sayfada net bir tarih (Haziran/Temmuz) bulunamadı."
            elif c.end_date and c.end_date.month == 6:
                status = "✅ DOĞRU UZATILMIŞ"
                reason = "Zaten 30 Haziran olarak bırakılmış/uzatılmış."
            else:
                status = "❓ BELİRSİZ"
                reason = f"Bitiş tarihi: {c.end_date}"
                
            return f"| {c.id} | {c.title[:40]} | {c.end_date} | {status} | {reason} |"
        else:
            return f"| {c.id} | {c.title[:40]} | {c.end_date} | ⚠️ ERİŞİM HATASI | HTTP {resp.status_code} |"
    except Exception as e:
        return f"| {c.id} | {c.title[:40]} | {c.end_date} | ⚠️ ERİŞİM HATASI | Bağlantı Koptu |"

def main():
    with open("extended_ids.txt", "r") as f:
        ids = [int(line.strip()) for line in f if line.strip()]
        
    with get_db_session() as db:
        camps = db.query(Campaign).filter(Campaign.id.in_(ids)).all()
        
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_url_and_classify, c): c for c in camps}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    # Sort results
    results.sort(key=lambda x: ("HATALI" in x, "DOĞRU" in x, x), reverse=True)
            
    with open("detailed_campaign_report.md", "w") as f:
        f.write("# Süresi Uzatılan Kampanyalar Analiz Raporu\n\n")
        f.write("| ID | Kampanya | DB Bitiş | Durum | Açıklama |\n")
        f.write("|---|---|---|---|---|\n")
        for r in results:
            f.write(r + "\n")
            
if __name__ == "__main__":
    main()
