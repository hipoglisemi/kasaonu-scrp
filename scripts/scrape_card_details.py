import asyncio
import json
import re
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
import os
from playwright.async_api import async_playwright

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DB_URL)

def get_active_cards():
    """DB'deki aktif kartları çek."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id, c.name, c.slug, b.name as bank_name
            FROM cards c
            LEFT JOIN banks b ON b.id = c.bank_id
            WHERE c.is_active = TRUE
            ORDER BY b.name, c.name
        """)
        return cur.fetchall()
    finally:
        conn.close()

def save_card_detail(card_id, detail):
    """card_details tablosuna kaydet."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO card_details (
                card_id, annual_fee, annual_fee_note, card_type,
                min_limit, max_limit, interest_rate, installment_max,
                rewards_type, rewards_rate, cashback_rate,
                features, pros, who_is_it_for, source_url, last_verified, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            ON CONFLICT (card_id) DO UPDATE SET
                annual_fee = EXCLUDED.annual_fee,
                annual_fee_note = EXCLUDED.annual_fee_note,
                card_type = EXCLUDED.card_type,
                min_limit = EXCLUDED.min_limit,
                max_limit = EXCLUDED.max_limit,
                interest_rate = EXCLUDED.interest_rate,
                installment_max = EXCLUDED.installment_max,
                rewards_type = EXCLUDED.rewards_type,
                rewards_rate = EXCLUDED.rewards_rate,
                cashback_rate = EXCLUDED.cashback_rate,
                features = EXCLUDED.features,
                pros = EXCLUDED.pros,
                who_is_it_for = EXCLUDED.who_is_it_for,
                source_url = EXCLUDED.source_url,
                last_verified = EXCLUDED.last_verified,
                updated_at = NOW()
        """, (
            card_id,
            detail.get("annual_fee"),
            detail.get("annual_fee_note"),
            detail.get("card_type"),
            detail.get("min_limit"),
            detail.get("max_limit"),
            detail.get("interest_rate"),
            detail.get("installment_max"),
            detail.get("rewards_type"),
            detail.get("rewards_rate"),
            detail.get("cashback_rate"),
            json.dumps(detail.get("features", []), ensure_ascii=False),
            json.dumps(detail.get("pros", []), ensure_ascii=False),
            detail.get("who_is_it_for"),
            detail.get("source_url"),
            datetime.now()
        ))
        conn.commit()
        print(f"  ✅  Kaydedildi: card_id={card_id}")
    except Exception as e:
        print(f"  ❌  DB hatası: {e}")
        conn.rollback()
    finally:
        conn.close()

async def scrape_hangikredi(page, card_name, bank_name):
    """
    HangiKredi'den belirli bir kartın bilgilerini çek.
    Kart adı + banka adıyla arama yap.
    """
    try:
        search_query = f"{bank_name} {card_name}"
        url = f"https://www.hangikredi.com/kredi-karti/sorgulama?q={search_query.replace(' ', '+')}"
        
        api_data = []
        
        # API isteklerini yakala
        async def handle_response(response):
            if any(x in response.url for x in [
                "/api/", "graphql", "kredi-karti", "cards", ".json"
            ]):
                try:
                    data = await response.json()
                    api_data.append({"url": response.url, "data": data})
                except:
                    pass
        
        page.on("response", handle_response)
        
        await page.goto(url, wait_until="networkidle", timeout=20000)
        
        # Sayfanın yüklenmesini bekle
        await page.wait_for_timeout(1500)

        # Aşağı kaydır — lazy load tetikle
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await page.wait_for_timeout(1000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
        
        # DOM'dan kart verilerini çek
        card_data = await page.evaluate("""
            () => {
                // Sayfadaki tüm metin bloklarını al
                const selectors = [
                    'article', 
                    '[class*="product"]',
                    '[class*="item"]', 
                    '[class*="result"]',
                    'li',
                    'section'
                ]
                
                let results = []
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel)
                    for (const el of els) {
                        const text = el.innerText?.trim()
                        if (text && text.length > 100 && text.length < 2000) {
                            results.push(text)
                        }
                    }
                    if (results.length >= 3) break
                }
                
                // Hiçbir şey bulunamazsa tüm body metnini al
                if (results.length === 0) {
                    results.push(document.body.innerText.slice(0, 3000))
                }
                
                return results.slice(0, 3)
            }
        """)
        
        # API verilerini de kontrol et
        for api in api_data:
            print(f"    API: {api['url'][:80]}")
        
        return {
            "dom_data": card_data,
            "api_data": api_data,
            "source_url": url
        }
        
    except Exception as e:
        print(f"    ⚠️  Scrape hatası: {e}")
        return None

async def scrape_hesapkurdu(page, card_name, bank_name):
    try:
        search_query = f"{bank_name} {card_name} kredi kartı"
        url = f"https://www.hesapkurdu.com/kredi-karti?q={search_query.replace(' ', '+')}"
        
        await page.goto(url, wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(1500)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await page.wait_for_timeout(1000)
        
        card_data = await page.evaluate("""
            () => {
                const body = document.body.innerText
                return [body.slice(0, 3000)]
            }
        """)
        
        return {
            "dom_data": card_data,
            "source_url": url
        }
    except Exception as e:
        print(f"    ⚠️  HesapKurdu hatası: {e}")
        return None

async def parse_with_gemini(raw_data, card_name, bank_name):
    """Gemini ile ham veriyi yapısal formata dönüştür."""
    from google import genai
    from google.genai import types
    
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY_1") or os.getenv("GEMINI_API_KEY_2"))
    
    content = "\n".join(raw_data.get("dom_data", []))[:3000]
    if not content:
        return None
    
    prompt = f"""
Aşağıdaki metin {bank_name} bankasının {card_name} 
kredi kartı hakkında bir web sayfasından alındı.

Bu metinden kart özelliklerini çıkar.
Bilgi yoksa veya emin değilsen null yaz.
SADECE aşağıdaki JSON formatını döndür, başka hiçbir şey yazma:

{{
  "annual_fee": "yıllık ücret (Ücretsiz veya TL cinsinden)",
  "annual_fee_note": "ek not (ilk yıl ücretsiz gibi)",
  "card_type": "Visa veya Mastercard veya Troy veya Amex",
  "min_limit": "minimum limit TL cinsinden",
  "max_limit": "maximum limit TL cinsinden",  
  "interest_rate": "aylık faiz oranı yüzde olarak",
  "installment_max": 12,
  "rewards_type": "puan sistemi adı (Chip-Para, Bonus, Mil, World Puan vs)",
  "rewards_rate": "kazanım oranı açıklaması",
  "cashback_rate": "nakit iade varsa yüzdesi",
  "features": ["en önemli 3-5 özellik"],
  "pros": ["en önemli 2-3 avantaj"],
  "who_is_it_for": "kime uygun, 1 cümle"
}}

ÖNEMLİ: 
- Markdown kullanma
- Açıklama ekleme  
- Sadece JSON döndür
- Emin olmadığın değerler için null yaz

METİN:
{content}
"""
    
    import time
    
    max_retries = 3
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemma-4-31b-it",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=1000
                )
            )
            break
        except Exception as e:
            error_str = str(e)
            if "503" in error_str or "429" in error_str:
                wait_time = (attempt + 1) * 5
                print(f"    ⏳  Gemini meşgul (503/429), {wait_time}s bekleniyor... (Deneme {attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                print(f"    ⚠️  Gemini API hatası: {e}")
                return None
                
    if not response or not hasattr(response, 'text') or not response.text:
        print("    ⚠️  API yanıt vermedi veya metin döndürmedi, atlanıyor.")
        return None
        
    text = str(response.text).strip()
    
    # Markdown temizle
    text = re.sub(r'```[a-z]*\n?', '', text).strip()
    text = re.sub(r'```', '', text).strip()
    
    # JSON bloğunu bul
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        text = json_match.group()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Tek tırnak varsa çift tırnağa çevir
        text = text.replace("'", '"')
        try:
            return json.loads(text)
        except:
            print(f"    ⚠️  JSON parse hatası")
            return None

async def main():
    print("🚀  Kart Bilgisi Scraper başlatıldı")
    print(f"📅  {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
    
    cards = get_active_cards()
    print(f"💳  {len(cards)} aktif kart bulundu\n")
    
    success = 0
    failed = 0
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="tr-TR"
        )
        page = await context.new_page()
        
        for i, (card_id, card_name, slug, bank_name) in enumerate(cards, 1):
            print(f"[{i}/{len(cards)}] {bank_name} — {card_name}")
            
            # Önce HangiKredi dene
            raw = await scrape_hangikredi(page, card_name, bank_name)
            
            # Veri gelmezse HesapKurdu dene
            if not raw or not raw.get("dom_data"):
                print(f"  ↩️  HesapKurdu deneniyor...")
                raw = await scrape_hesapkurdu(page, card_name, bank_name)
            
            if raw and raw.get("dom_data"):
                # Gemini ile parse et
                detail = await parse_with_gemini(raw, card_name, bank_name)
                
                if detail:
                    detail["source_url"] = raw["source_url"]
                    save_card_detail(card_id, detail)
                    success += 1
                else:
                    print(f"  ⚠️  Parse edilemedi")
                    failed += 1
            else:
                print(f"  ⚠️  Veri çekilemedi")
                failed += 1
            
            # Rate limiting
            await page.wait_for_timeout(1000)
        
        await browser.close()
    
    print(f"\n{'='*50}")
    print(f"✅  Başarılı: {success}")
    print(f"❌  Başarısız: {failed}")
    print(f"{'='*50}")
    print("✨  Tamamlandı")

if __name__ == "__main__":
    asyncio.run(main())
