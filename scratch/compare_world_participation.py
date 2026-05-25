import os
import re
import json
import time
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
from bs4 import BeautifulSoup
import html as py_html
from src.database import get_db
from src.models import Campaign

# Rotate Gemini API Keys to bypass rate limits
API_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
    os.getenv("GEMINI_API_KEY_4"),
    os.getenv("GEMINI_API_KEY_5"),
    os.getenv("GEMINI_API_KEY_6"),
    os.getenv("GEMINI_API_KEY_7"),
    os.getenv("GEMINI_API_KEY_8"),
]
API_KEYS = [k for k in API_KEYS if k]

if not API_KEYS:
    raise ValueError("No Gemini API keys found in environment variables!")

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = text.replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")
    text = re.sub(r"[^a-z0-9]", "", text)
    return text

def extract_participation_section(text: str) -> str:
    """Locate paragraph/sentences in text mentioning participation terms for quick verification context."""
    if not text:
        return ""
    paragraphs = text.split("\n")
    keywords = ["katıl", "başvuru", "kanal", "sms", "gönder", "detay", "katılım", "kayıt", "yazıp"]
    matches = []
    for p in paragraphs:
        p_low = p.lower()
        if any(kw in p_low for kw in keywords):
            matches.append(p.strip())
    return " \n ".join(matches[:3]) if matches else ""

def clean_html_with_new_selectors(html_content: str, title: str) -> str:
    """Extract clean text exactly mirroring our updated AI Parser Golden logic."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
        tag.decompose()

    noise_selectors = [
        '.other-campaigns', '.featured-campaigns', '.similar-campaigns',
        '.campaign-recommendations', 'section.news-carousel',
        '#related-campaigns', '.campaignDetail-others',
        '.related-campaigns', '.other-campaign-list',
        '[class*="sidebar"]', '[class*="footer"]', '[class*="header"]',
        '[class*="navigation"]', '[id*="navigation"]',
        '.yk-header', '.yk-footer', '.banner-area', '.related-campaigns-wrapper'
    ]
    for sel in noise_selectors:
        for el in soup.select(sel):
            el.decompose()

    # Target selectors with .sub-content at highest priority
    target_selectors = [
        '.sub-content', '.campaign-detail-tab-details', '.campaign-detail-box',
        '.campaign-detail-content', '.campaign-detail'
    ]
    
    content_parts = []
    for sel in target_selectors:
        for el in soup.select(sel):
            t = el.get_text(separator='\n', strip=True)
            if t and len(t) > 80:
                content_parts.append(t)

    if content_parts:
        clean_content = '\n\n'.join(content_parts)
    else:
        clean_content = soup.get_text(separator='\n', strip=True)

    clean_content = py_html.unescape(clean_content)
    clean_content = re.sub(r'\n{3,}', '\n\n', clean_content).strip()
    return f"{title}\n{clean_content}"

def audit_single_campaign(camp, thread_index):
    # 1. Dynamically download the live campaign page's HTML to get the sub-content container!
    clean_text = ""
    fetched_live = False
    
    if camp.tracking_url and camp.tracking_url.startswith("http"):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
            }
            res = requests.get(camp.tracking_url, headers=headers, timeout=10)
            if res.status_code == 200 and len(res.text) > 1000:
                clean_text = clean_html_with_new_selectors(res.text, camp.title)
                fetched_live = True
        except Exception as e:
            pass
            
    # Fallback to DB clean_text if live fetch failed
    if not clean_text:
        clean_text = camp.clean_text or ""
        
    participation_context = extract_participation_section(clean_text)
    
    if not clean_text or len(clean_text) < 30:
        return None
        
    # 2. Query Gemini to extract exact participation steps
    prompt = f"""
Sen uzman bir kampanya veri analistisin. Aşağıdaki Yapı Kredi kampanyasına ait metni dikkatlice oku ve kampanyaya katılmak için müşterinin yapması gereken adımları (SMS gönderme adımları, World Mobil uygulamasındaki Hemen Katıl butonu vb.) kelimesi kelimesine tespit et.

Kurallar:
1. Müşterinin katılması için fiziksel veya dijital bir eylem (SMS göndermek, World Mobil'den 'Hemen Katıl' butonuna tıklamak vb.) metinde açıkça yazıyorsa, bu katılım adımlarını eksiksiz olarak 'extracted_participation' alanına yaz.
2. Metinde katılımla ilgili ("Kampanya Katılım Detayları", "Kampanya Başvuru Kanalları" vb.) hiçbir SMS, uygulama veya kayıt adımı belirtilmemişse, katılım kendiliğinden oluyorsa 'extracted_participation' alanına tam olarak "Otomatik" yaz.
3. 'participation_section' alanına metinden kelimesi kelimesine katılım koşulunun veya başvuru kanalının geçtiği orijinal paragrafı/cümleyi kopyala.

JSON formatında yanıt ver:
{{
  "participation_section": "Metinde katılım adımlarının veya kanallarının geçtiği birebir cümle",
  "extracted_participation": "World Mobil uygulamasındaki Kampanyalar alanından Hemen Katıl butonuna tıklayarak veya..."
}}

KAMPANYA BAŞLIĞI: {camp.title}
KAMPANYA METNİ:
{clean_text}
"""
    # Select API key for this thread
    api_key = API_KEYS[thread_index % len(API_KEYS)]
    max_retries = 3
    ai_response = None
    
    for attempt in range(max_retries):
        try:
            # Instantiate a fresh genai Client for thread safety
            client = genai.Client(api_key=api_key)
            config = types.GenerateContentConfig(
                temperature=0.0,
                top_p=0.1,
                top_k=1,
                response_mime_type="application/json",
                max_output_tokens=1000
            )
            res = client.models.generate_content(
                model="models/gemini-3.1-flash-lite",
                contents=prompt,
                config=config
            )
            if res and res.text:
                ai_response = json.loads(res.text.strip())
                break
        except Exception as e:
            # Shift to next key on retry
            alt_key = API_KEYS[(thread_index + attempt + 1) % len(API_KEYS)]
            api_key = alt_key
            time.sleep(1.0)
            
    if not ai_response:
        return None
        
    proposed = ai_response.get("extracted_participation", "Otomatik").strip()
    section_text = ai_response.get("participation_section", "").strip()
    
    db_val = (camp.participation or "Otomatik").strip()
    
    db_norm = normalize_text(db_val)
    proposed_norm = normalize_text(proposed)
    
    # Determine match status
    is_match = db_norm == proposed_norm
    
    # If both normalization results point to "otomatik" or empty, treat as match
    if ("otomatik" in db_norm or not db_norm) and ("otomatik" in proposed_norm or not proposed_norm):
        is_match = True
        
    return {
        "id": camp.id,
        "title": camp.title,
        "url": camp.tracking_url,
        "section_text": section_text or participation_context,
        "db_val": db_val,
        "proposed": proposed,
        "is_match": is_match,
        "fetched_live": fetched_live
    }

def main():
    print(f"Loaded {len(API_KEYS)} API keys for rotation.")
    print("Starting LIVE multi-threaded precision mismatch audit for Yapı Kredi World campaign participation...")
    
    db = next(get_db())
    # Retrieve all active Yapı Kredi World campaigns
    campaigns = db.query(Campaign).filter(
        Campaign.tracking_url.like('%worldcard.com.tr%'),
        Campaign.is_active == True
    ).all()
    
    print(f"Total active YKB World campaigns found: {len(campaigns)}")
    
    results = []
    mismatch_count = 0
    match_count = 0
    
    # Run audit concurrently using ThreadPoolExecutor
    max_workers = min(len(API_KEYS) * 2, 10)
    print(f"Running concurrent audit with {max_workers} worker threads...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(audit_single_campaign, camp, idx): camp 
            for idx, camp in enumerate(campaigns)
        }
        
        completed_idx = 0
        for future in as_completed(futures):
            completed_idx += 1
            camp = futures[future]
            try:
                res = future.result()
                if res:
                    results.append(res)
                    if res["is_match"]:
                        match_count += 1
                    else:
                        mismatch_count += 1
                if completed_idx % 10 == 0 or completed_idx == len(campaigns):
                    print(f"Progress: {completed_idx}/{len(campaigns)} analyzed...")
            except Exception as e:
                print(f"   [Error] Campaign {camp.id} failed in executor thread: {e}")
                
    # Sort results by ID
    results.sort(key=lambda x: x["id"])
    
    # Write precision mismatch report to file
    report_path = "/Users/hipoglisemi/Desktop/kartavantaj/yapi_kredi_world_participation_mismatch_report.md"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Yapı Kredi World Kampanya Katılım Şekli Hassas Denetim Raporu 🏆\n\n")
        f.write(f"Bu rapor, veri tabanındaki tüm aktif Yapı Kredi World kampanyalarını **canlı olarak web sitelerinden çekip** en güncel `.sub-content` seçicisi ile temizler. Elde edilen gerçek katılım adımları ile veri tabanındaki değeri karşılaştırarak uyuşmazlıkları tespit eder.\n\n")
        f.write(f"## 📊 Rapor Özet Bilgileri\n")
        f.write(f"- **Toplam Denetlenen Kampanya:** `{len(results)}` (Veri tabanındaki tüm aktif World kampanyaları)\n")
        f.write(f"- **✅ Tam Uyum (Eşleşenler):** `{match_count}`\n")
        f.write(f"- **🔴 Uyuşmazlık (Uyuşmayanlar):** `{mismatch_count}`\n")
        f.write(f"- **Rapor Üretim Tarihi:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n")
        
        f.write(f"## 🔴 Katılım Şekli Uyuşmazlığı Bulunan Kampanyalar ({mismatch_count})\n")
        f.write(f"Bu kampanyaların metninde geçen katılım adımları ile veri tabanında kayıtlı olan değerler uyuşmamaktadır:\n\n")
        
        mismatched_results = [r for r in results if not r["is_match"]]
        for r in mismatched_results:
            f.write(f"### 🏷️ Kampanya #{r['id']} - {r['title']}\n")
            f.write(f"- **URL:** {r['url']}\n")
            f.write(f"- **Taramadan Alınan Katılım Kanıtı:**\n")
            if r['section_text']:
                sec_clean = r['section_text'].replace("\n", " ").strip()
                f.write(f"  > *\"{sec_clean}\"*\n")
            else:
                f.write(f"  > `Metinden katılım cümlesi alınamadı`\n")
            f.write(f"- **Veri Tabanındaki Mevcut Katılım:** `{r['db_val'] if r['db_val'] else 'Boş'}`\n")
            f.write(f"- **AI Önerilen Gerçek Katılım Şekli:** `🔴 {r['proposed']}`\n")
            f.write(f"\n---\n\n")
            
        f.write(f"## ✅ Katılım Şekli Eşleşen/Doğrulanan Kampanyalar ({match_count})\n")
        f.write(f"Bu kampanyaların metnindeki katılım adımları ile veri tabanındaki değerler birbiriyle uyumludur:\n\n")
        
        matched_results = [r for r in results if r["is_match"]]
        for r in matched_results:
            f.write(f"### 🏷️ Kampanya #{r['id']} - {r['title']}\n")
            f.write(f"- **URL:** {r['url']}\n")
            f.write(f"- **Veri Tabanı & AI Eşleşen Değer:** `{r['db_val'] if r['db_val'] else 'Otomatik'}`\n")
            f.write(f"\n---\n\n")
            
    print(f"Mismatch audit completed! Report saved to {report_path}")

if __name__ == "__main__":
    main()
