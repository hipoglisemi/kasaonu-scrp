import os
import time
import psycopg2
from dotenv import load_dotenv
from slugify import slugify
from google import genai
from google.genai import types

load_dotenv()

# ── Veritabanı ──────────────────────────────────────────────────────────────
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL must be set in .env")

# ── Gemini 2.5 Flash ─────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY must be set in .env")

client = genai.Client(api_key=GEMINI_API_KEY)

# ── Unsplash görselleri ──────────────────────────────────────────────────────
COVER_IMAGES = [
    "https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=1000&q=80",
    "https://images.unsplash.com/photo-1563013544-824ae1b704d3?w=1000&q=80",
    "https://images.unsplash.com/photo-1553729459-efe14ef6055d?w=1000&q=80",
    "https://images.unsplash.com/photo-1579621970563-ebec7560ff3e?w=1000&q=80",
    "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?w=1000&q=80",
    "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?w=1000&q=80",
    "https://images.unsplash.com/photo-1523240715632-99045506a591?w=1000&q=80",
    "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=1000&q=80",
]


# ── Veritabanı yardımcıları ──────────────────────────────────────────────────

def get_connection():
    return psycopg2.connect(DB_URL)


def get_existing_titles():
    """Daha önce yazılmış blog başlıklarını çek (duplicate önleme)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute('SELECT LOWER(title) FROM blogs')
        return {row[0].strip() for row in cur.fetchall()}
    except Exception as e:
        print(f"⚠️  Mevcut bloglar çekilemedi: {e}")
        return set()
    finally:
        conn.close()


def get_banks_and_sectors():
    """Aktif banka ve sektörleri çek."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, slug FROM banks WHERE is_active = TRUE ORDER BY id")
        banks = cur.fetchall()
        cur.execute("SELECT id, name, slug FROM sectors WHERE is_active = TRUE ORDER BY sort_order")
        sectors = cur.fetchall()
        return banks, sectors
    finally:
        conn.close()


def get_top_campaigns(bank_id=None, sector_id=None, limit=5):
    """
    Belirli bir banka veya sektörün en kaliteli aktif kampanyalarını çek.
    Blog yazısına somut örnek olarak kullanılacak.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT c.title, c.reward_text, c.end_date, b.name AS bank_name, s.name AS sector_name
            FROM campaigns c
            LEFT JOIN banks b ON b.id = (
                SELECT bank_id FROM cards WHERE id = c.card_id LIMIT 1
            )
            LEFT JOIN sectors s ON s.id = c.sector_id
            WHERE c.is_active = TRUE
        """
        params = []
        if bank_id:
            query += " AND b.id = %s"
            params.append(bank_id)
        if sector_id:
            query += " AND c.sector_id = %s"
            params.append(sector_id)
        query += " ORDER BY c.quality_score DESC NULLS LAST LIMIT %s"
        params.append(limit)
        cur.execute(query, params)
        return cur.fetchall()
    except Exception as e:
        print(f"⚠️  Kampanyalar çekilemedi: {e}")
        return []
    finally:
        conn.close()


def save_to_database(title, slug, content_html, excerpt, meta_description, image_url):
    """
    Blogu veritabanına kaydet.
    is_published = False → admin panelinden onaylanana kadar yayınlanmaz.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO blogs
              (title, slug, content_html, meta_description, image_url, category, is_published, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE, NOW())
            RETURNING id
            """,
            (title, slug, content_html, meta_description, image_url, "Rehber"),
        )
        blog_id = cur.fetchone()[0]
        conn.commit()
        print(f"✅  Blog kaydedildi (TASLAK) — ID: {blog_id} | /blog/{slug}")
        return blog_id
    except Exception as e:
        print(f"❌  Veritabanı hatası: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


# ── Konu üreteci ─────────────────────────────────────────────────────────────

TOPIC_TEMPLATES = [
    ("{bank} Kredi Kartı Kampanyaları {year} — En İyi Fırsatlar", "bank"),
    ("{sector} Alışverişinde En Çok Kazandıran Kredi Kartları {year}", "sector"),
    ("{bank} ile {sector} Harcamalarında Maksimum Avantaj", "bank_sector"),
    ("En İyi {sector} Kredi Kartı Kampanyaları {year} — Karşılaştırma", "sector"),
    ("{bank} Kredi Kartı ile {sector}'da Nasıl Tasarruf Edilir?", "bank_sector"),
    ("Türkiye'nin En İyi {sector} İndirimli Kredi Kartları", "sector"),
    ("{bank} Kampanyaları: {sector} Kategorisinde Öne Çıkan Teklifler", "bank_sector"),
]


def generate_topics(banks, sectors, existing_titles, year=2026):
    """Banka + sektör kombinasyonlarından yazılmamış konu listesi üret."""
    topics = []
    for template, ttype in TOPIC_TEMPLATES:
        if ttype == "bank":
            for bank in banks:
                title = template.format(bank=bank[1], year=year)
                if title.lower() not in existing_titles:
                    topics.append({"title": title, "bank": bank, "sector": None})
        elif ttype == "sector":
            for sector in sectors:
                title = template.format(sector=sector[1], year=year)
                if title.lower() not in existing_titles:
                    topics.append({"title": title, "bank": None, "sector": sector})
        elif ttype == "bank_sector":
            for bank in banks[:5]:   # ilk 5 banka yeterli
                for sector in sectors[:6]:  # ilk 6 sektör
                    title = template.format(bank=bank[1], sector=sector[1], year=year)
                    if title.lower() not in existing_titles:
                        topics.append({"title": title, "bank": bank, "sector": sector})
    return topics


# ── Gemini çağrıları ─────────────────────────────────────────────────────────

def build_campaign_context(bank, sector):
    """Kampanya verilerini prompt'a eklenecek metin bloğuna dönüştür."""
    campaigns = get_top_campaigns(
        bank_id=bank[0] if bank else None,
        sector_id=sector[0] if sector else None,
    )
    if not campaigns:
        return ""
    lines = ["Aşağıdaki gerçek kampanyalar bu yazıda referans olarak kullanılabilir:\n"]
    for c in campaigns:
        title, reward, end_date, bank_name, sector_name = c
        end_str = end_date.strftime("%d.%m.%Y") if end_date else "Süresiz"
        lines.append(f"• {bank_name or ''} — {title}: {reward or ''} (Son: {end_str})")
    return "\n".join(lines)


def generate_article(topic_title, bank, sector):
    """Gemini 2.5 Flash ile SEO makalesi üret."""
    print(f"✍️   Makale üretiliyor: {topic_title}")
    campaign_context = build_campaign_context(bank, sector)

    prompt = f"""
Sen KartAvantaj'ın kıdemli finans editörüsün. 
Görevin: Aşağıdaki konu için Google'da üst sıralara çıkacak, 
gerçek kullanıcıya değer katan, özgün ve derinlemesine bir blog makalesi yazmak.

KONU: "{topic_title}"

{campaign_context}

YAZIM KURALLARI:
1. Uzunluk: 1000-1300 kelime. Ne fazla ne az.
2. Dil: Kusursuz Türkçe. Samimi ama profesyonel ton.
   Okuyucuya "siz" diye hitap et.
3. Yapı: Giriş → 3-4 ana bölüm (h2) → Alt başlıklar (h3) → Sonuç ve CTA
4. Format: Sadece HTML. <p>, <h2>, <h3>, <ul>, <li>, <strong>, <em> kullan.
   <h1> KULLANMA. Markdown KULLANMA.
5. SEO: Konu başlığındaki anahtar kelimeleri doğal biçimde ilk paragrafta,
   h2 başlıklarında ve sonuç bölümünde kullan.
6. Değer: Soyut bilgi verme. Somut rakamlar, gerçek kampanya örnekleri,
   pratik ipuçları içersin. Okuyucu makaleyi okuyunca ne yapacağını bilsin.
7. CTA: Son paragrafta "KartAvantaj'da tüm kampanyaları karşılaştır" 
   mesajını doğal bir cümleyle ver.

SADECE makale HTML'ini döndür. Başka hiçbir şey yazma.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=8000,
        ),
    )
    html = response.text.strip()
    # Markdown kod bloğu gelirse temizle
    if html.startswith("```html"):
        html = html[7:]
    if html.startswith("```"):
        html = html[3:]
    if html.endswith("```"):
        html = html[:-3]
    return html.strip()


def generate_meta(topic_title, html_content):
    """Kısa ve tıklanabilir meta description üret."""
    print("📝  Meta description üretiliyor...")
    prompt = f"""
Aşağıdaki blog makalesi için Google arama sonuçlarında görünecek 
meta description yaz.

Kurallar:
- Maksimum 155 karakter
- Türkçe, tıklamaya teşvik eden
- Konu başlığındaki anahtar kelimeleri içersin
- Sona "KartAvantaj'da incele" gibi kısa bir CTA ekle
- SADECE meta description metnini döndür, başka hiçbir şey yazma

Konu: {topic_title}
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=200,
        ),
    )
    return response.text.strip()


def generate_excerpt(meta_description):
    """Meta description'dan kısa excerpt türet."""
    return meta_description[:160] if meta_description else ""


# ── Ana akış ─────────────────────────────────────────────────────────────────

def main():
    import random

    print("🚀  KartAvantaj SEO Blog Üreticisi başlatıldı")

    existing_titles = get_existing_titles()
    banks, sectors = get_banks_and_sectors()

    print(f"🏦  {len(banks)} aktif banka, 📁 {len(sectors)} aktif sektör bulundu")

    topics = generate_topics(banks, sectors, existing_titles)

    if not topics:
        print("📭  Yazılacak yeni konu bulunamadı. Tüm kombinasyonlar mevcut.")
        return

    print(f"📋  {len(topics)} yeni konu mevcut")

    topic = random.choice(topics)
    title = topic["title"]
    bank = topic["bank"]
    sector = topic["sector"]
    image_url = random.choice(COVER_IMAGES)

    print(f"📝  Seçilen konu: {title}")

    # İçerik üret
    html_content = generate_article(title, bank, sector)
    meta_description = generate_meta(title, html_content)
    excerpt = generate_excerpt(meta_description)

    # Temiz slug — timestamp yok
    slug = slugify(title)

    # Slug çakışması varsa sonuna yıl ekle
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM blogs WHERE slug = %s", (slug,))
        if cur.fetchone()[0] > 0:
            slug = f"{slug}-2026"
    finally:
        conn.close()

    # Kaydet (taslak olarak)
    save_to_database(title, slug, html_content, excerpt, meta_description, image_url)

    print("✨  Tamamlandı. Blog admin panelinden onaylanmayı bekliyor.")


if __name__ == "__main__":
    main()