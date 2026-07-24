import os
import psycopg2
import requests
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load local environment variables (.env file) if present
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgres://postgres:OKaNWkuA52DaZoaTsGm6gCCqTgk03W9PXsFIWsc77NhTAGwZID3wqOel58mkOsBB@localhost:5434/postgres"
)

# Domain mapping to detect domain mismatch anomalies
BANK_DOMAINS = {
    "halkbank": ["paraf.com.tr", "halkbank.com.tr", "parafly.com.tr", "parafgenc.com.tr"],
    "paraf": ["paraf.com.tr", "halkbank.com.tr", "parafly.com.tr", "parafgenc.com.tr"],
    "akbank": ["axess.com.tr", "akbank.com", "wingscard.com.tr", "kartfree.com"],
    "axess": ["axess.com.tr", "akbank.com", "wingscard.com.tr", "kartfree.com"],
    "yapıkredi": ["worldcard.com.tr", "yapikredi.com.tr"],
    "world": ["worldcard.com.tr", "yapikredi.com.tr"],
    "işbankası": ["isbank.com.tr", "maximiles.com.tr"],
    "maximiles": ["isbank.com.tr", "maximiles.com.tr"],
    "garanti": ["bonus.com.tr", "garantibbva.com.tr", "milesandsmiles", "shopandfly.com.tr"],
    "qnb": ["qnbfinansbank.com", "cardfinans.com", "milesandsmiles", "qnbcard.com.tr"],
    "teb": ["teb.com.tr", "cepteteb.com.tr"],
    "dünyakatılım": ["dunyakatilim.com.tr"],
    "emlakkatılım": ["emlakkatilim.com.tr"],
    "ziraat": ["ziraatbank.com.tr", "ziraatkatilim.com.tr", "bankkart.com.tr", "ziraatdinamik.com.tr"],
    "tami": ["tami.com.tr"],
    "shell": ["shell.com.tr"],
    "opet": ["opet.com.tr"],
    "tom": ["tombankhadi.com"],
    "hadi": ["tombankhadi.com"],
    "turktelekom": ["turktelekom.com.tr", "selfy.com.tr"],
    "alternatifbank": ["alternatifbank.com.tr"],
    "vakıf": ["vakifbank.com.tr", "vakifkart.com.tr"],
    "vakıfkatılım": ["vakifkatilim.com.tr"]
}

def clean_bank_name(name):
    if not name:
        return ""
    return name.lower().replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ç", "c").replace("ü", "u").replace("ö", "o").replace(" ", "")

def check_url_anomaly(bank_name, tracking_url):
    if not bank_name or not tracking_url:
        return False, "Eksik veri"
    
    parsed_url = urlparse(tracking_url)
    domain = parsed_url.netloc.lower()
    
    clean_bank = clean_bank_name(bank_name)
    
    # Try to find a matching bank key in our domain mapping
    matched_key = None
    for k in BANK_DOMAINS.keys():
        if k in clean_bank:
            matched_key = k
            break
            
    if not matched_key:
        return False, "Bilinmeyen banka alan adı eşleşmesi"
        
    allowed_domains = BANK_DOMAINS[matched_key]
    is_valid = any(d in domain for d in allowed_domains)
    
    if not is_valid:
        return True, f"Banka '{bank_name}' iken URL domaini '{domain}' (Uyumsuzluk!)"
        
    return False, "Normal"

def send_telegram_alert(anomalies):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️ Telegram credentials not found in environment. Skipping alert.")
        return
        
    message = "🚨 *KASAONU - ŞÜPHELİ UZATILAN KAMPANYALAR* 🚨\n"
    message += f"Toplam Hatalı Kampanya: *{len(anomalies)}*\n"
    message += "==================================\n\n"
    
    # Send up to 10 anomalies in one message to avoid hitting telegram character limit
    for idx, a in enumerate(anomalies[:10]):
        message += f"*{idx+1}. Kampanya ID: #{a['id']}*\n"
        message += f"• *Başlık:* {a['title']}\n"
        message += f"• *Banka/Kart:* {a['bank']} - {a['card']}\n"
        message += f"• *Hatalar:*\n"
        for r in a['reasons']:
            message += f"  ❌ {r}\n"
        message += f"• [Kampanya Linki]({a['url']})\n"
        message += "----------------------------------\n"
        
    if len(anomalies) > 10:
        message += f"\nve {len(anomalies) - 10} adet daha şüpheli kampanya var. Detaylar için GitHub loglarına bakın."
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✉️ Telegram alert sent successfully.")
        else:
            print(f"⚠️ Failed to send Telegram alert: {response.text}")
    except Exception as e:
        print(f"⚠️ Error sending Telegram alert: {e}")

def run_system_audit():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 1. Find when the system went live (Earliest date_extended=true campaign)
    cur.execute("""
        SELECT min(updated_at) as live_date 
        FROM campaigns 
        WHERE date_extended = true
    """)
    live_row = cur.fetchone()
    live_date = live_row["live_date"] if live_row and live_row["live_date"] else None
    
    if not live_date:
        print("❌ Veritabanında hiçbir date_extended = true kampanyası bulunamadı!")
        cur.close()
        conn.close()
        return
 
    print(f"\n🚀 SİSTEMİN DEVREYE GİRİŞ TARİHİ (MİLAT): {live_date}")
    print("==========================================================================")
    
    # 2. Fetch all date_extended=true campaigns from that day onwards
    cur.execute("""
        SELECT 
            c.id, 
            c.title, 
            c."description", 
            c."tracking_url" as trackingUrl, 
            c."card_id" as cardId, 
            card.name as cardName,
            bank.name as bankName,
            c."is_approved" as isApproved, 
            c."date_extended" as dateExtended,
            c."start_date" as startDate,
            c."end_date" as endDate,
            c."created_at" as createdAt,
            c."updated_at" as updatedAt,
            c."eligible_cards" as eligibleCards
                FROM "campaigns" c
        LEFT JOIN "cards" card ON card.id = c.card_id
        LEFT JOIN "banks" bank ON bank.id = card.bank_id
        WHERE c.date_extended = true AND c.is_active = true AND c.updated_at >= %s
        ORDER BY c.updated_at DESC
    """, (live_date,))
    
    rows = cur.fetchall()
    print(f"📊 Toplam Analiz Edilecek Kampanya Sayısı: {len(rows)}")
    print("==========================================================================")
    
    corrupted_count = 0
    clean_count = 0
    
    anomalies_log = []
    
    for c in rows:
        c_id = c["id"]
        title = c["title"]
        bank_name = c["bankname"]
        card_name = c["cardname"]
        tracking_url = c["trackingurl"]
        eligible_cards = c["eligiblecards"]
        desc = c["description"]
        start_date = c["startdate"]
        end_date = c["enddate"]
        
        has_anomaly = False
        reasons = []
        
        # Check URL domain anomalies
        is_url_anomaly, url_reason = check_url_anomaly(bank_name, tracking_url)
        if is_url_anomaly:
            has_anomaly = True
            reasons.append(url_reason)
            
        # Check for empty card anomalies
        if not eligible_cards or eligible_cards.strip() in ["-", "", "None"]:
            has_anomaly = True
            reasons.append("Geçerli kartlar alanı bomboş veya '-' yazılmış.")
            
        # Check for empty description anomalies
        if not desc or len(desc.strip()) < 10:
            has_anomaly = True
            reasons.append("Açıklama alanı bomboş veya çok kısa (hayalet kampanya).")
            
        # Check for abnormal date ranges (e.g. only extended for 1-2 days)
        if start_date and end_date:
            date_diff = (end_date - start_date).days
            if date_diff <= 2:
                has_anomaly = True
                reasons.append(f"Tarih aralığı aşırı şüpheli: {start_date} -> {end_date} (Sadece {date_diff} gün geçerli!)")
                
        if has_anomaly:
            corrupted_count += 1
            anomalies_log.append({
                "id": c_id,
                "title": title,
                "bank": bank_name,
                "card": card_name,
                "url": tracking_url,
                "reasons": reasons,
                "updated_at": c["updatedat"]
            })
        else:
            clean_count += 1
 
    # Print anomalies
    print(f"\n🚨 TOPLAM TESPİT EDİLEN BOZUK KAMPANYA: {corrupted_count}")
    print(f"✅ HATA İÇERMEYEN OTOMATİK UZATILAN: {clean_count}")
    print("==========================================================================\n")
    
    for idx, a in enumerate(anomalies_log):
        print(f"{idx+1}. Kampanya ID: #{a['id']}")
        print(f"   Başlık: {a['title']}")
        print(f"   Banka/Kart: {a['bank']} - {a['card']}")
        print(f"   Giriş URL: {a['url']}")
        print(f"   Hatalar:")
        for r in a['reasons']:
            print(f"     ❌ {r}")
        print(f"   Tarihçe: {a['updated_at'].strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 74)
 
    # Write Markdown file
    md_path = "/Users/hipoglisemi/Desktop/kasaonu/anomalies_report.md"
    if not os.path.exists(os.path.dirname(md_path)):
        md_path = "anomalies_report.md"  # fallback to current directory
        
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 🚨 Kasaonu - Şüpheli Uzatılan Kampanyalar Raporu\n\n")
        f.write(f"Bu rapor otomatik oluşturulmuştur. Toplam şüpheli kampanya sayısı: **{len(anomalies_log)}**\n\n")
        f.write("Aşağıdaki listeden hatalı kampanyaları inceleyebilir ve düzelttikçe işaretleyebilirsiniz:\n\n")
        
        for idx, a in enumerate(anomalies_log):
            f.write(f"### - [ ] {idx+1}. ID: #{a['id']} - {a['title']}\n")
            f.write(f"- **Banka / Kart:** {a['bank']} - {a['card']}\n")
            f.write(f"- **Uzatılma Tarihi:** {a['updated_at'].strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- **Kaynak Linki:** [{a['url']}]({a['url']})\n")
            f.write("- **Tespit Edilen Hatalar:**\n")
            for r in a["reasons"]:
                f.write(f"  - ❌ {r}\n")
            f.write("\n---\n\n")
            
    print(f"✅ Markdown report generated: {md_path}")
 
    # Send Telegram alert if any anomalies found
    if anomalies_log:
        send_telegram_alert(anomalies_log)
 
    cur.close()
    conn.close()

if __name__ == "__main__":
    run_system_audit()
