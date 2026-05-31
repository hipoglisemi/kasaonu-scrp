import os
import sys
import json
from datetime import datetime, timedelta, timezone
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Setup path to include project root for src.* imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign
from dotenv import load_dotenv
load_dotenv('.env')

urllib3.disable_warnings()

import re
from google.genai import types # type: ignore
from src.utils.gemini_client import generate_with_rotation

def clean_html_to_text(html: str) -> str:
    """Removes script, style, nav, and other HTML tags to produce clean text."""
    if not html:
        return ""
    text = re.sub(r'<(script|style|head|nav|footer)[^>]*>([\s\S]*?)<\/\1>', ' ', html)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:8000] # Limit to 8000 characters to keep tokens tiny

def extract_end_date_via_ai(title: str, html: str):
    """
    Extracts only the campaign end date from the campaign HTML text using Gemini.
    Returns date string in YYYY-MM-DD format, or None if not found/error.
    """
    clean_text = clean_html_to_text(html)
    if not clean_text:
        return None
        
    system_instruction = (
        "Sen KartAvantaj projesinde sadece kampanya bitiş tarihlerini tespit eden uzman bir veri analistisin.\n"
        "Gönderilen metni analiz ederek kampanyanın son geçerlilik tarihini (bitiş tarihini) bulmalısın.\n\n"
        "Kurallar:\n"
        "1. Tarihi YYYY-MM-DD formatında döndür.\n"
        "2. Metinde açıkça yazan kampanya bitiş tarihini tespit et. (Örnek: '30 Haziran 2026', '31.12.2026' vb.)\n"
        "3. Çıktıyı her zaman belirtilen JSON formatında ver.\n"
    )
    
    prompt = f"""
KAMPANYA BAŞLIĞI: {title}
KAMPANYA SAYFA METNİ:
---
{clean_text}
---

GÖREV: Sayfa metnini ve kampanya başlığını inceleyerek kampanyanın son geçerlilik tarihini tespit et. Çıktıyı kesinlikle aşağıdaki JSON şemasına göre üret:

```json
{{
  "end_date": "YYYY-MM-DD" // Tespit edilen tarih (örn. "2026-06-30"), eğer kesin olarak bulunamadıysa null.
}}
```
"""
    config = types.GenerateContentConfig(
        temperature=0.0,
        top_p=0.1,
        top_k=1,
        response_mime_type="application/json",
        system_instruction=system_instruction
    )
    
    try:
        result_str = generate_with_rotation(
            prompt=prompt,
            model="gemma-4-31b-it",
            config=config
        )
        
        if not result_str:
            return None
            
        cleaned_result = result_str.strip()
        if cleaned_result.startswith("```"):
            lines = cleaned_result.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_result = "\n".join(lines).strip()
            
        # Clean any single-quote malformations directly on this quick response
        if "'" in cleaned_result:
            cleaned_result = cleaned_result.replace("'", '"')
            
        data = json.loads(cleaned_result)
        return data.get("end_date")
    except Exception as e:
        print(f"      ⚠️  Tarih çıkartma hatası: {e}")
        return None

def proactive_expiry_audit(max_audits=2000):
    """
    Checks campaigns expiring TODAY.
    Fetches their tracking URL and parses them with AI to get the actual end_date.
    If a date in the future (later than current end_date) is found, updates it.
    This prevents unnecessary deactivations and rescraping/AI parsing cost.
    """
    print("🕰️ Starting Proactive Expiry Audit (Grace Period check via AI)...")
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
    
    # Fetch campaigns expiring strictly today
    campaigns_to_audit = []
    try:
        with get_db_session() as db:
            soon_expiring = db.query(Campaign).filter(
                Campaign.is_active == True,
                Campaign.end_date == today,
                Campaign.tracking_url.isnot(None)
            ).all()
            
            campaigns_to_audit = [
                {
                    "id": c.id,
                    "url": c.tracking_url,
                    "title": c.title,
                    "end_date": c.end_date
                }
                for c in soon_expiring
            ]
    except Exception as e:
        print(f"   ⚠️ Error fetching soon expiring campaigns: {e}")
        return
        
    if not campaigns_to_audit:
        print("✅ No campaigns expiring within the next 3 days.")
        return
        
    print(f"🔍 Found {len(campaigns_to_audit)} campaigns expiring soon. Checking for extension using AI...")
    
    # Sort campaigns to prioritize those expiring earliest
    campaigns_to_audit.sort(key=lambda x: x["end_date"])
    
    # Cap audits per run to protect API quotas (default 150)
    if len(campaigns_to_audit) > max_audits:
        print(f"⚡ Capping AI audits to the top {max_audits} soonest-expiring campaigns.")
        campaigns_to_audit = campaigns_to_audit[:max_audits]
        
    extended_count = 0
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'})
    
    # Fetch HTML pages in parallel first to speed up the network bottleneck
    print(f"🌐 Fetching {len(campaigns_to_audit)} campaign pages in parallel...")
    campaigns_with_html = []
    
    def fetch_html(c):
        try:
            resp = session.get(c["url"], allow_redirects=True, timeout=15, verify=False)
            if resp.status_code == 200:
                return {**c, "html": resp.text}
        except Exception:
            pass
        return None
        
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_html, c) for c in campaigns_to_audit]
        for future in as_completed(futures):
            res = future.result()
            if res:
                campaigns_with_html.append(res)
                 
    print(f"📥 Successfully fetched {len(campaigns_with_html)} pages. Starting AI parsing sequentially...")
    
    for idx, c in enumerate(campaigns_with_html):
        url = c["url"]
        current_end = c["end_date"]
        html = c["html"]
        try:
            # Fixed 5s sleep to stay safe under 15 RPM
            if idx > 0:
                time.sleep(5.0)
            
            ai_end_date_str = extract_end_date_via_ai(c["title"], html)
            if not ai_end_date_str:
                continue
                
            try:
                latest_date = datetime.strptime(ai_end_date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            
            # Safety range: must be strictly later than current_end and no more than 1 year in the future
            if latest_date > current_end and latest_date <= today + timedelta(days=365):
                print(f"   🎉 Campaign Extended via AI! '{c['title']}'")
                print(f"      Old End Date: {current_end} ➔ New End Date: {latest_date}")
                
                # Update in DB
                with get_db_session() as db:
                    db_camp = db.query(Campaign).filter(Campaign.id == c["id"]).first()
                    if db_camp:
                        db_camp.end_date = latest_date
                        db_camp.updated_at = datetime.now()
                        db.commit()
                        extended_count += 1
        except Exception as e:
            print(f"   ⚠️ Error auditing {c['title']} with AI: {e}")
            
        if (idx + 1) % 25 == 0:
            print(f"   📊 Progress: {idx + 1}/{len(campaigns_with_html)} audited, {extended_count} extended so far...")
            
    print(f"✅ Proactive Expiry Audit complete. Extended {extended_count} campaigns.")

if __name__ == "__main__":
    max_audits = 2000
    if len(sys.argv) > 1:
        try:
            max_audits = int(sys.argv[1])
        except ValueError:
            pass
    proactive_expiry_audit(max_audits=max_audits)
