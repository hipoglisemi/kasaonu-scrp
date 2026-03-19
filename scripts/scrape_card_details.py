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
                features, pros, who_is_it_for, source_url, last_verified
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
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
        await page.wait_for_timeout(2000)
        
        # DOM'dan kart verilerini çek
        card_data = await page.evaluate("""
            (cardName) => {
                const cards = document.querySelectorAll(
                    '[class*="card"], [class*="product"], article, [data-testid]'
                )
                const results = []
                for (const card of cards) {
                    const text = card.innerText
                    if (text && text.toLowerCase().includes(cardName.toLowerCase())) {
                        results.push(text.slice(0, 500))
                    }
                }
                return results
            }
        """, card_name)
        
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

async def parse_with_gemini(raw_data, card_name, bank_name):
    """Gemini ile ham veriyi yapısal formata dönüştür."""
    from google import genai
    from google.genai import types
    
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    content = "\n".join(raw_data.get("dom_data", []))[:3000]
    if not content:
        return None
    
    prompt = f"""
{bank_name} bankasının {card_name} kredi kartı hakkında aşağıdaki veri var.
Bu veriden kart özelliklerini çıkar ve SADECE JSON döndür:

{{
  "annual_fee": "yıllık ücret (örn: Ücretsiz veya 500 TL/yıl)",
  "annual_fee_note": "ek not varsa (örn: ilk yıl ücretsiz)",
  "card_type": "Visa/Mastercard/Troy/Amex",
  "min_limit": "minimum limit (örn: 3.000 TL)",
  "max_limit": "maksimum limit (örn: 150.000 TL)",
  "interest_rate": "aylık faiz oranı (örn: %4,99)",
  "installment_max": 12,
  "rewards_type": "puan sistemi (örn: Chip-Para, Bonus, Mil)",
  "rewards_rate": "kazanım oranı (örn: 100 TL = 1 Chip-Para)",
  "cashback_rate": "nakit iade oranı varsa",
  "features": ["özellik1", "özellik2", "özellik3"],
  "pros": ["avantaj1", "avantaj2"],
  "who_is_it_for": "kime uygun (1-2 cümle)"
}}

Bilgi yoksa null yaz. SADECE JSON döndür.

VERİ:
{content}
"""
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=1000
        )
    )
    
    text = response.text.strip()
    if text.startswith("```"):
        text = re.sub(r"```[a-z]*\n?", "", text).strip()
    
    try:
        return json.loads(text)
    except:
        print(f"    ⚠️  JSON parse hatası: {text[:100]}")
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
            
            # HangiKredi'den çek
            raw = await scrape_hangikredi(page, card_name, bank_name)
            
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
            await page.wait_for_timeout(2000)
        
        await browser.close()
    
    print(f"\n{'='*50}")
    print(f"✅  Başarılı: {success}")
    print(f"❌  Başarısız: {failed}")
    print(f"{'='*50}")
    print("✨  Tamamlandı")

if __name__ == "__main__":
    asyncio.run(main())
