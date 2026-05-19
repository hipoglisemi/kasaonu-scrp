import sys, os, time
sys.path.insert(0, '/Users/hipoglisemi/Desktop/kartavantaj-scraper')
from src.database import get_db_session
from src.models import Campaign
from dotenv import load_dotenv
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import json

warnings.filterwarnings('ignore')

load_dotenv('/Users/hipoglisemi/Desktop/kartavantaj-scraper/.env')
api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=api_key)

model = genai.GenerativeModel('models/gemma-4-31b-it')

PROMPT_TEMPLATE = """Sen banka kampanya metinlerindeki "negatif anlamı" (hariçtir, dahil değildir, sadece şunlar geçerlidir) çözmekte uzman bir denetçisin.
Aşağıda bankanın şartları ve sistemin ayıkladığı kartlar verilmiştir. 

Banka Şartları:
{conditions}

Sistemin Ayıkladığı Kartlar:
{eligible_cards}

LÜTFEN ADIM ADIM DÜŞÜNEREK (Chain of Thought) YANIT VER:
Adım 1: Banka şartlarını oku ve AÇIKÇA "Dahil değildir, hariçtir, geçerli değildir, faydalanılamaz" denen kart isimlerini bul (Örn: Ticari kartlar, Sanal kartlar, Bankomat kartlar vb.)
Adım 2: Sistemin listesinde bu yasaklı kartlardan herhangi biri yazılmış mı?
Adım 3: Banka metninde "Sadece Bireysel kartlar" gibi sınırlayıcı bir ifade varken, sistem listeye "Ticari/Corporate/Business" kartlardan birini koymuş mu?

Eğer Adım 2 veya Adım 3'te bir eşleşme (hata) bulursan, sonucun kesinlikle FAIL olmalıdır!
Eğer hiçbir hata yoksa, sonucun PASS olmalıdır.

YANIT FORMATI:
Sadece JSON dön.
{{
  "step_1_excluded": "Hariç tutulanları buraya yaz",
  "step_2_conflict": "Çakışma var mı? Açıkla",
  "step_3_commercial_error": "Ticari/Bireysel hatası var mı? Açıkla",
  "status": "PASS veya FAIL",
  "reason": "Eğer FAIL ise kısa sebep, PASS ise boş bırak"
}}
"""

def analyze_campaign(c):
    if not c.conditions or not c.eligible_cards:
        return None
        
    prompt = PROMPT_TEMPLATE.format(
        conditions=c.conditions + " " + (c.description or ""),
        eligible_cards=c.eligible_cards
    )
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            
            # JSON formatını güvenli şekilde parse etmeye çalış
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            if start_idx != -1 and end_idx != -1:
                json_str = text[start_idx:end_idx+1]
                data = json.loads(json_str)
                
                if data.get("status") == "FAIL":
                    return {
                        'id': c.id,
                        'title': c.title,
                        'url': c.tracking_url,
                        'ai_cards': c.eligible_cards,
                        'reason': data.get("reason"),
                        'step_1': data.get("step_1_excluded"),
                        'step_2': data.get("step_2_conflict")
                    }
                return None 
        except Exception as e:
            if "429" in str(e):
                time.sleep(10 * (attempt + 1))
            else:
                time.sleep(2)
    return None

def main():
    with get_db_session() as db:
        active_camps = db.query(Campaign).filter(
            Campaign.is_active == True,
            Campaign.eligible_cards.isnot(None),
            Campaign.conditions.isnot(None)
        ).all()
    
    print(f"AI Auditor (Chain of Thought - V2) Başlıyor... Toplam {len(active_camps)} kampanya analiz edilecek.", flush=True)
    
    with open('/Users/hipoglisemi/Desktop/kartavantaj-scraper/GEMMA_31B_DENETIM_RAPORU.md', 'w', encoding='utf-8') as f:
        f.write('# GEMMA 4 31B IT - KESİN VERİ KALİTESİ RAPORU (ZORLU DENETİM)\n')
        f.write(f'**Taranacak Toplam Kampanya:** {len(active_camps)}\n\n')
    
    failures = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_camp = {executor.submit(analyze_campaign, c): c for c in active_camps}
        
        count = 0
        for future in as_completed(future_to_camp):
            count += 1
            try:
                res = future.result()
                if res:
                    failures.append(res)
                    print(f"❌ [FAIL] ID: {res['id']} | {res['reason']}", flush=True)
                    
                    with open('/Users/hipoglisemi/Desktop/kartavantaj-scraper/GEMMA_31B_DENETIM_RAPORU.md', 'a', encoding='utf-8') as f:
                        f.write(f'### 🚨 ID: {res["id"]} | {res["title"]}\n')
                        f.write(f'- **Gemma Adım 1 (Yasaklılar):** {res["step_1"]}\n')
                        f.write(f'- **Gemma Analizi (Çelişki):** {res["step_2"]}\n')
                        f.write(f'- **Sistemin Yanlış Kartları:** {res["ai_cards"]}\n')
                        f.write(f'- **URL:** {res["url"]}\n\n')
            except Exception as e:
                pass
            
            if count % 10 == 0:
                print(f"⚙️ İlerleme: {count}/{len(active_camps)} tamamlandı. (Bulunan Hata Sayısı: {len(failures)})", flush=True)
                
    print(f"\n✅ DENETİM BİTTİ! Toplam Hata: {len(failures)}", flush=True)

if __name__ == '__main__':
    main()
