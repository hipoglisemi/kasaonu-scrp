import os
import psycopg2  # type: ignore
from typing import List, Tuple, Set, Dict, Optional, Any, cast
from dotenv import load_dotenv  # type: ignore
from slugify import slugify  # type: ignore
from src.utils.gemini_client import generate_with_rotation  # type: ignore

load_dotenv()

# ── Veritabanı ──────────────────────────────────────────────────────────────
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL must be set in .env")

# ── Gemini modeli (3'lü key rotation kullanılır) ─────────────────────────────
BLOG_MODEL = os.getenv("BLOG_MODEL", "gemini-2.5-flash")

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


def get_existing_titles() -> Set[str]:
    """Daha önce yazılmış blog başlıklarını çek (duplicate önleme)."""
    titles: Set[str] = set()
    conn: Optional[Any] = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('SELECT LOWER(title) FROM blogs')
        rows = cur.fetchall()
        if rows:
            titles = {row[0].strip() for row in rows}
    except Exception as e:
        print(f"⚠️  Mevcut bloglar çekilemedi: {e}")
    finally:
        if conn:
            conn.close()
    return titles


def get_banks_and_sectors() -> Tuple[List[Any], List[Any]]:
    """Aktif banka ve sektörleri çek."""
    banks: List[Any] = []
    sectors: List[Any] = []
    conn: Optional[Any] = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, slug FROM banks WHERE is_active = TRUE ORDER BY id")
        banks = list(cur.fetchall() or [])
        cur.execute("SELECT id, name, slug FROM sectors WHERE is_active = TRUE ORDER BY sort_order")
        sectors = list(cur.fetchall() or [])
    except Exception as e:
        print(f"⚠️  Banka/sektör listesi çekilemedi: {e}")
    finally:
        if conn:
            conn.close()
    return banks, sectors


def get_top_campaigns(bank_id=None, sector_id=None, limit=5):
    """
    Belirli bir banka veya sektörün en kaliteli aktif kampanyalarını çek.
    Blog yazısına somut örnek olarak kullanılacak.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT c.title, c.reward_text, c.end_date, b.name AS bank_name, s.name AS sector_name, c.slug
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

TOPIC_TEMPLATES: List[Tuple[str, str]] = [
    ("{bank} Kredi Kartı Kampanyaları {year} — En İyi Fırsatlar", "bank"),
    ("{sector} Alışverişinde En Çok Kazandıran Kredi Kartları {year}", "sector"),
    ("{bank} ile {sector} Harcamalarında Maksimum Avantaj", "bank_sector"),
    ("En İyi {sector} Kredi Kartı Kampanyaları {year} — Karşılaştırma", "sector"),
    ("{bank} Kredi Kartı ile {sector}'da Nasıl Tasarruf Edilir?", "bank_sector"),
    ("Türkiye'nin En İyi {sector} İndirimli Kredi Kartları", "sector"),
    ("{bank} Kampanyaları: {sector} Kategorisinde Öne Çıkan Teklifler", "bank_sector"),
]


def generate_topics(banks: List[Any], sectors: List[Any], existing_titles: Set[str], year: int = 2026) -> List[Dict[str, Any]]:
    """Banka + sektör kombinasyonlarından yazılmamış konu listesi üret."""
    topics: List[Dict[str, Any]] = []
    for template_raw, ttype in TOPIC_TEMPLATES:
        template = str(template_raw)
        if ttype == "bank":
            for bank in cast(List[Any], banks):
                title = template.format(bank=bank[1], year=year)
                if title.lower() not in existing_titles:
                    topics.append({"title": title, "bank": bank, "sector": None})
        elif ttype == "sector":
            for sector in cast(List[Any], sectors):
                title = template.format(sector=sector[1], year=year)
                if title.lower() not in existing_titles:
                    topics.append({"title": title, "bank": None, "sector": sector})
        elif ttype == "bank_sector":
            # List[Any] de'ki indexing uyarısını Any cast ile aşalım
            selected_banks = cast(Any, banks)[:5]
            selected_sectors = cast(Any, sectors)[:6]
            for bank in selected_banks:
                for sector in selected_sectors:
                    # IDE uyarısını gidermek için Any cast ve ignore kullanalım
                    title = cast(Any, template).format(bank=bank[1], sector=sector[1], year=year)  # type: ignore
                    if title.lower() not in existing_titles:
                        topics.append({"title": title, "bank": bank, "sector": sector})
    return topics


# ── Gemini çağrıları ─────────────────────────────────────────────────────────

def build_campaign_context(bank: Optional[Any], sector: Optional[Any]) -> str:
    """Kampanya verilerini prompt'a eklenecek metin bloğuna dönüştür."""
    campaigns = get_top_campaigns(
        bank_id=bank[0] if bank else None,
        sector_id=sector[0] if sector else None,
    )
    if not campaigns:
        return ""
    lines = ["Aşağıdaki gerçek kampanyalar bu yazıda referans olarak kullanılabilir:\n"]
    for c in campaigns:
        # campaigns explicitly typed or checked
        c_title, c_reward, c_end_date, c_bank_name, c_sector_name, c_slug = c
        end_str = c_end_date.strftime("%d.%m.%Y") if c_end_date else "Süresiz"
        url = f"https://kartavantaj.com/kampanya/{c_slug}" if c_slug else ""
        lines.append(f"• {c_bank_name or ''} — {c_title}: {c_reward or ''} (Son: {end_str}) | Link: {url}")
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
4. Format: Sadece HTML. <p>, <h2>, <h3>, <ul>, <li>, <strong>, <em>, <a> kullan.
   <h1> KULLANMA. Markdown KULLANMA.
5. SEO ve Linkleme: Konu başlığındaki anahtar kelimeleri doğal biçimde ilk paragrafta,
   h2 başlıklarında ve sonuç bölümünde kullan.
   ÖNEMLİ: Listelenen her kampanya için verilen kampanya linkini (URL) <a href="..."> etiketi kullanarak metin içine doğal bir şekilde ekle!
6. Değer: Soyut bilgi verme. Somut rakamlar, gerçek kampanya örnekleri,
   pratik ipuçları içersin. Okuyucu makaleyi okuyunca ne yapacağını bilsin.
7. CTA: Son paragrafta "KartAvantaj'da tüm kampanyaları karşılaştır" 
   mesajını doğal bir cümleyle ver.

SADECE makale HTML'ini döndür. Başka hiçbir şey yazma.
"""

    html = generate_with_rotation(
        prompt=prompt,
        model=BLOG_MODEL,
        temperature=0.7,
        max_output_tokens=8000,
    )
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
    return generate_with_rotation(
        prompt=prompt,
        model=BLOG_MODEL,
        temperature=0.3,
        max_output_tokens=200,
    )


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