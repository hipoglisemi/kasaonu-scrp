import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SEARCH_CONSOLE_KEY = os.getenv("SEARCH_CONSOLE_KEY")
SITE_URL = "sc-domain:kartavantaj.com"

def get_service():
    key_data = json.loads(SEARCH_CONSOLE_KEY)
    print(f"DEBUG: Using key for: {key_data.get('client_email')}")
    credentials = service_account.Credentials.from_service_account_info(
        key_data,
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
    )
    return build("searchconsole", "v1", credentials=credentials)

def get_date_range(days_ago_start, days_ago_end=3):
    end = datetime.now() - timedelta(days=days_ago_end)
    start = datetime.now() - timedelta(days=days_ago_start)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def query(service, start, end, dimensions, filters=None, limit=10):
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": dimensions,
        "rowLimit": limit,
        "orderBy": [{"fieldName": "clicks", "sortOrder": "DESCENDING"}]
    }
    if filters:
        body["dimensionFilterGroups"] = filters
    try:
        r = service.searchanalytics().query(
            siteUrl=SITE_URL, body=body
        ).execute()
        return r.get("rows", [])
    except Exception as e:
        print(f"⚠️  Hata: {e}")
        return []

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def main():
    print("🔍  KartAvantaj SEO Performans Raporu")
    print(f"📅  {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    service = get_service()

    # Tarih aralıkları
    s7, e7 = get_date_range(10, 3)      # Son 7 gün
    s28, e28 = get_date_range(31, 3)    # Son 28 gün
    prev_s, prev_e = get_date_range(38, 10)  # Önceki 28 gün

    # ── 1. GENEL ÖZET ──
    print_section("1. GENEL PERFORMANS (Son 28 gün vs Önceki 28 gün)")

    def get_totals(start, end):
        body = {
            "startDate": start, "endDate": end, "dimensions": []
        }
        try:
            r = service.searchanalytics().query(
                siteUrl=SITE_URL, body=body
            ).execute()
            rows = r.get("rows", [])
            return rows[0] if rows else {}
        except:
            return {}

    cur = get_totals(s28, e28)
    prev = get_totals(prev_s, prev_e)

    def pct(a, b):
        if not b: return "—"
        diff = ((a - b) / b) * 100
        arrow = "▲" if diff > 0 else "▼"
        return f"{arrow} {abs(diff):.1f}%"

    print(f"  Tıklama:    {int(cur.get('clicks',0)):,}  "
          f"(önceki: {int(prev.get('clicks',0)):,})  "
          f"{pct(cur.get('clicks',0), prev.get('clicks',0))}")
    print(f"  Gösterim:   {int(cur.get('impressions',0)):,}  "
          f"(önceki: {int(prev.get('impressions',0)):,})  "
          f"{pct(cur.get('impressions',0), prev.get('impressions',0))}")
    print(f"  Ort. CTR:   {cur.get('ctr',0)*100:.2f}%  "
          f"(önceki: {prev.get('ctr',0)*100:.2f}%)")
    print(f"  Ort. Pozisyon: {cur.get('position',0):.1f}  "
          f"(önceki: {prev.get('position',0):.1f})")

    # ── 2. EN ÇOK TIKLANMA ──
    print_section("2. EN ÇOK TIKLANAN SORGULAR (Son 28 gün)")
    rows = query(service, s28, e28, ["query"], limit=15)
    for i, row in enumerate(rows, 1):
        q = row.get("keys", [""])[0]
        clicks = int(row.get("clicks", 0))
        pos = row.get("position", 0)
        print(f"  {i:2}. {q:<45} "
              f"Tıklama: {clicks:4}  Pozisyon: {pos:.1f}")

    # ── 3. POZİSYON ANALİZİ ──
    print_section("3. POZİSYON DAĞILIMI (Son 28 gün)")
    rows = query(service, s28, e28, ["query"], limit=500)

    pos_1_3 = [r for r in rows if r.get("position", 99) <= 3]
    pos_4_10 = [r for r in rows if 3 < r.get("position", 99) <= 10]
    pos_11_20 = [r for r in rows if 10 < r.get("position", 99) <= 20]
    pos_21_plus = [r for r in rows if r.get("position", 99) > 20]

    print(f"  🥇 1-3. sıra (ilk 3):     {len(pos_1_3):4} sorgu")
    print(f"  🥈 4-10. sıra (1. sayfa): {len(pos_4_10):4} sorgu")
    print(f"  🥉 11-20. sıra (2. sayfa):{len(pos_11_20):4} sorgu")
    print(f"  📉 21+. sıra (derin):     {len(pos_21_plus):4} sorgu")

    print(f"\n  İlk 3'teki sorgular:")
    for r in sorted(pos_1_3, key=lambda x: x.get("clicks",0), reverse=True)[:10]:
        q = r.get("keys", [""])[0]
        pos = r.get("position", 0)
        clicks = int(r.get("clicks", 0))
        print(f"    ✅ {q:<45} Pos: {pos:.1f}  Tıklama: {clicks}")

    # ── 4. BÜYÜME FIRSATları ──
    print_section("4. BÜYÜME FIRSATLARI (1. sayfada ama az tıklama)")
    low_ctr = [
        r for r in rows
        if 4 <= r.get("position", 99) <= 10
        and r.get("impressions", 0) > 50
        and r.get("ctr", 0) < 0.05
    ]
    low_ctr.sort(key=lambda x: x.get("impressions", 0), reverse=True)

    print("  (1. sayfada ama CTR düşük — title/description iyileştirilebilir)")
    for r in low_ctr[:10]:
        q = r.get("keys", [""])[0]
        pos = r.get("position", 0)
        impressions = int(r.get("impressions", 0))
        ctr = r.get("ctr", 0) * 100
        print(f"  ⚡ {q:<45} "
              f"Pos: {pos:.1f}  Gösterim: {impressions}  CTR: {ctr:.1f}%")

    # ── 5. EN İYİ SAYFALAR ──
    print_section("5. EN ÇOK TIKLANAN SAYFALAR (Son 28 gün)")
    rows = query(service, s28, e28, ["page"], limit=15)
    for i, row in enumerate(rows, 1):
        page = row.get("keys", [""])[0].replace(SITE_URL, "")
        clicks = int(row.get("clicks", 0))
        pos = row.get("position", 0)
        print(f"  {i:2}. {page:<50} "
              f"Tıklama: {clicks:4}  Pozisyon: {pos:.1f}")

    # ── 6. SON 7 GÜN TREND ──
    print_section("6. SON 7 GÜN TREND")
    rows_7 = query(service, s7, e7, ["query"], limit=10)
    print("  Bu hafta en çok tıklanan sorgular:")
    for i, row in enumerate(rows_7, 1):
        q = row.get("keys", [""])[0]
        clicks = int(row.get("clicks", 0))
        pos = row.get("position", 0)
        print(f"  {i:2}. {q:<45} "
              f"Tıklama: {clicks:4}  Pozisyon: {pos:.1f}")

    # ── 7. HEDEF KELİMELER ──
    print_section("7. HEDEF KELİMELER KONTROLÜ")
    target_keywords = [
        "kredi kartı kampanyası",
        "kredi kartı avantajı",
        "market kredi kartı",
        "akaryakıt kampanya",
        "kredi kartı karşılaştırma",
        "en iyi kredi kartı",
    ]

    all_rows = query(service, s28, e28, ["query"], limit=1000)
    keyword_map = {
        r.get("keys", [""])[0]: r for r in all_rows
    }

    for kw in target_keywords:
        # Tam eşleşme veya içeren sorgular
        matches = [
            r for r in all_rows
            if kw.lower() in r.get("keys", [""])[0].lower()
        ]
        if matches:
            best = max(matches, key=lambda x: x.get("clicks", 0))
            q = best.get("keys", [""])[0]
            pos = best.get("position", 0)
            clicks = int(best.get("clicks", 0))
            status = "🟢" if pos <= 10 else "🟡" if pos <= 20 else "🔴"
            print(f"  {status} '{kw}'")
            print(f"     En iyi: '{q}'  "
                  f"Pozisyon: {pos:.1f}  Tıklama: {clicks}")
        else:
            print(f"  ⚪ '{kw}' — henüz veri yok")

    print(f"\n{'='*60}")
    print("  ✨ Rapor tamamlandı")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
