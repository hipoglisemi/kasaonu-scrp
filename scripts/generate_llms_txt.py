import os
import psycopg2
from dotenv import load_dotenv

# Load env from scraper or parent directory
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    # Try parent directory
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'kasaonu', '.env.local'))
    DB_URL = os.getenv("DATABASE_URL")

def build_llms_files():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("SELECT name, slug FROM banks WHERE is_active = true ORDER BY name;")
    banks = cur.fetchall()

    cur.execute("SELECT name, slug FROM sectors WHERE is_active = true ORDER BY name;")
    sectors = cur.fetchall()

    cur.execute("SELECT name, slug FROM cards WHERE is_active = true ORDER BY name;")
    cards = cur.fetchall()

    cur.execute("""
        SELECT DISTINCT b.name, b.slug 
        FROM brands b 
        JOIN campaign_brands cb ON b.id = cb.brand_id 
        JOIN campaigns c ON cb.campaign_id = c.id 
        WHERE b.is_active = true AND c.is_active = true AND c.is_approved = true 
        ORDER BY b.name;
    """)
    active_brands = cur.fetchall()

    cur.execute("""
        SELECT slug, title FROM blogs WHERE is_published = true ORDER BY created_at DESC LIMIT 30;
    """)
    blogs = cur.fetchall()

    conn.close()

    domain = os.getenv("SITE_DOMAIN") or os.getenv("NEXT_PUBLIC_SITE_URL", "https://kartavantaj.com").replace("https://", "").replace("http://", "").rstrip("/")
    base_url = f"https://{domain}"

    # 1. Standard llms.txt (Complete organized structure)
    llms_lines = [
        "# Kasaonu",
        "",
        "> Kasaonu, Türkiye'deki bankaların ve kuruluşların tüm kredi kartı kampanyalarını (chip-para, puan, mil, indirim ve taksit avantajları) anlık ve günlük doğrulamayla karşılaştıran bağımsız platformdur.",
        "",
        "## Ana Dizin ve Özellikler",
        f"- [Tüm Kampanyalar]({base_url}/kampanyalar): En güncel kredi kartı kampanya listesi.",
        f"- [Tüm Kredi Kartları]({base_url}/kartlar): Türkiye'deki 70+ kredi kartının detaylı özellikleri ve puan sistemleri.",
        f"- [Tüm Markalar]({base_url}/markalar): 1200+ markaya özel indirim ve kampanya sayfaları.",
        f"- [Blog & Rehberler]({base_url}/blog): Kart kullanım rehberleri, puan kazanma taktikleri ve mil hesaplamaları.",
        "",
        f"## Sektör ve Kategori Sayfaları (Toplam {len(sectors)} Sektör)",
    ]

    for s_name, s_slug in sectors:
        llms_lines.append(f"- [{s_name} Kampanyaları]({base_url}/kategori/{s_slug})")

    llms_lines.append(f"\n## Bankalar ve Finans Kuruluşları (Toplam {len(banks)} Banka/Kuruluş)")
    for b_name, b_slug in banks:
        llms_lines.append(f"- [{b_name} Kampanyaları]({base_url}/banka/{b_slug})")

    llms_lines.append(f"\n## Kredi Kartları (Toplam {len(cards)} Kart)")
    for c_name, c_slug in cards:
        llms_lines.append(f"- [{c_name}]({base_url}/kart/{c_slug})")

    llms_lines.append(f"\n## Popüler Markalar (Aktif Kampanyalı {len(active_brands)} Marka)")
    for br_name, br_slug in active_brands[:60]: # Top 60 brands in main llms.txt
        llms_lines.append(f"- [{br_name} Kampanyaları]({base_url}/marka/{br_slug})")

    if len(active_brands) > 60:
        llms_lines.append(f"- [Tüm Markalar Listesi ({len(active_brands)} Marka)]({base_url}/markalar)")

    if blogs:
        llms_lines.append("\n## En Son Yayınlanan Rehberler & Bloglar")
        for bg_slug, bg_title in blogs:
            llms_lines.append(f"- [{bg_title}]({base_url}/blog/{bg_slug})")

    llms_lines.extend([
        "",
        "## Kurumsal Bilgiler",
        f"- [Hakkımızda]({base_url}/kurumsal/hakkimizda): Platform vizyonu ve yayın politikası.",
        f"- [İletişim]({base_url}/kurumsal/iletisim): İletişim bilgileri ve destek.",
        "",
        "Not: Bu dosya LLM (Yapay Zeka) modelleri için hazırlanmış içerik indeksidir. Sayfaların güncel detay verileri HTML üzerindeki JSON-LD (schema.org) yapılandırılmış verilerindedir."
    ])

    content_llms = "\n".join(llms_lines)

    # Write to target paths
    target_paths = [
        "/Users/hipoglisemi/Desktop/kasaonu/public/llms.txt",
        "/Users/hipoglisemi/Desktop/files/llms.txt"
    ]

    for p in target_paths:
        with open(p, "w", encoding="utf-8") as f:
            f.write(content_llms)
        print(f"✅ Güncellendi: {p}")

    # 2. Complete llms-full.txt (Includes ALL 1234 Brands)
    llms_full_lines = list(llms_lines)
    # Replace top brands section with ALL brands
    brand_header_idx = -1
    for idx, line in enumerate(llms_full_lines):
        if "## Popüler Markalar" in line:
            brand_header_idx = idx
            break
    
    if brand_header_idx != -1:
        full_brand_section = [f"## Tüm Markalar ({len(active_brands)} Aktif Marka)"]
        for br_name, br_slug in active_brands:
            full_brand_section.append(f"- [{br_name} Kampanyaları]({base_url}/marka/{br_slug})")
        
        # Find next section index (En Son Yayınlanan Rehberler or Kurumsal)
        next_sec_idx = brand_header_idx + 1
        while next_sec_idx < len(llms_full_lines) and not llms_full_lines[next_sec_idx].startswith("## "):
            next_sec_idx += 1
        
        llms_full_lines = llms_full_lines[:brand_header_idx] + full_brand_section + llms_full_lines[next_sec_idx:]

    content_full = "\n".join(llms_full_lines)

    full_target_paths = [
        "/Users/hipoglisemi/Desktop/kasaonu/public/llms-full.txt",
        "/Users/hipoglisemi/Desktop/files/llms-full.txt"
    ]

    for fp in full_target_paths:
        with open(fp, "w", encoding="utf-8") as f:
            f.write(content_full)
        print(f"✅ Güncellendi: {fp}")

    print(f"🎉 İşlem Tamam! Toplam: {len(banks)} Banka, {len(sectors)} Sektör, {len(cards)} Kart, {len(active_brands)} Marka eklendi!")

if __name__ == "__main__":
    build_llms_files()
