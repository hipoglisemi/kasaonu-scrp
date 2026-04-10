"""
Bulk AI Marketing Text Generator (Template-Based, No API)
==========================================================
Gemini API kullanmadan, kampanya verisinden (başlık, ödül, sektör, banka)
şablon tabanlı enerjik, emojili pazarlama metinleri üretir.
"""
import os
import sys
import random
import re

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    print("❌ DATABASE_URL bulunamadı.")
    sys.exit(1)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

# ─── Sektör bazlı emoji ve CTA havuzu ───
SECTOR_CONFIG = {
    'market': {'emojis': ['🛒', '🛍️', '🥦', '🧺'], 'cta': ['Market alışverişinizde büyük avantaj!', 'Alışverişin tadını çıkarın!']},
    'akaryakit': {'emojis': ['⛽', '🚗', '🏎️', '🔥'], 'cta': ['Deponuzu doldururken cebiniz dolsun!', 'Yakıt harcamalarınızda kazanın!']},
    'restoran-kafe': {'emojis': ['🍕', '☕', '🍔', '🍽️'], 'cta': ['Lezzetli fırsatı kaçırmayın!', 'Yemek keyfinize avantaj katın!']},
    'e-ticaret': {'emojis': ['🛒', '📦', '💻', '🎯'], 'cta': ['Online alışverişte büyük fırsat!', 'Tıkla, kazan, keyfini çıkar!']},
    'giyim-aksesuar': {'emojis': ['👗', '👟', '🧥', '✨'], 'cta': ['Tarzınızı yansıtırken kazanın!', 'Moda dünyasında avantajlı alışveriş!']},
    'turizm-konaklama': {'emojis': ['✈️', '🏨', '🌍', '🏖️'], 'cta': ['Tatil planlarınızı ertelemeyin!', 'Hayalinizdeki tatile avantajlı uçun!']},
    'ulasim': {'emojis': ['🚌', '✈️', '🚇', '🛫'], 'cta': ['Yolculuğunuza avantaj katın!', 'Ulaşımda tasarruf fırsatı!']},
    'dijital-platform': {'emojis': ['🎮', '🎬', '🎵', '📱'], 'cta': ['Dijital dünyada kazanmaya başlayın!', 'Eğlencenize avantaj ekleyin!']},
    'saglik-guzellik': {'emojis': ['💊', '💆', '🏥', '✨'], 'cta': ['Sağlığınıza yatırım yapın!', 'Güzellik rutininize avantaj katın!']},
    'sigorta': {'emojis': ['🛡️', '🏠', '🚗', '💼'], 'cta': ['Geleceğinizi güvenceye alın!', 'Sigortanızda avantajlı fiyatlar!']},
    'egitim-kitap': {'emojis': ['📚', '🎓', '📖', '✏️'], 'cta': ['Bilgiye yatırım yapın!', 'Eğitim harcamalarınızda kazanın!']},
    'elektronik': {'emojis': ['📱', '💻', '🖥️', '🎧'], 'cta': ['Teknoloji tutkunlarına müjde!', 'Elektronik alışverişinde süper fırsat!']},
    'mobilya-dekorasyon': {'emojis': ['🏠', '🛋️', '🪑', '🏡'], 'cta': ['Evinizi yenilerken kazanın!', 'Dekorasyon alışverişinde süper avantaj!']},
    'finans-yatirim': {'emojis': ['💰', '📈', '🏦', '💳'], 'cta': ['Finansal avantajınızı artırın!', 'Yatırımlarınızda bir adım öne geçin!']},
    'fatura-telekomunikasyon': {'emojis': ['📱', '📡', '💬', '🔋'], 'cta': ['İletişim harcamalarınızda kazanın!', 'Faturanızı öderken avantaj yakalayın!']},
}

DEFAULT_CONFIG = {'emojis': ['💳', '🎉', '🚀', '✨'], 'cta': ['Bu fırsatı kaçırmayın!', 'Hemen avantajdan yararlanın!']}

# ─── Reward type bazlı şablonlar ───
REWARD_TEMPLATES = {
    'taksit': [
        "{title} fırsatıyla alışverişlerinizi taksitle yapın {emoji1} Peşin fiyatına {reward} imkanını yakalayın, bütçenizi rahatlatın! {emoji2}",
        "Ödemelerinizi bölerken avantajı kaçırmayın {emoji1} {reward} fırsatıyla alışverişinizi planlarken cebiniz gülsün! {emoji2}",
    ],
    'puan': [
        "{title} kampanyasıyla harcamalarınız puana dönüşsün {emoji1} {reward} kazanma fırsatı sizi bekliyor, hemen katılın! {emoji2}",
        "Harcadıkça kazanın {emoji1} {title} ile {reward} biriktirin ve avantajların tadını çıkarın! {emoji2}",
    ],
    'indirim': [
        "{title} ile büyük indirim fırsatı {emoji1} {reward} avantajıyla alışverişin keyfini sürün, bu fırsat kaçmaz! {emoji2}",
        "İndirim rüzgarı esiyor {emoji1} {title} kampanyasında {reward} fırsatını yakalayın! {emoji2}",
    ],
    'cashback': [
        "{title} ile harcamanız geri dönsün {emoji1} {reward} nakit iade avantajını kaçırmayın! {emoji2}",
        "Harcayın, geri kazanın {emoji1} {title} kampanyasıyla {reward} iade fırsatı tam size göre! {emoji2}",
    ],
    'mil': [
        "Mil biriktirmenin tam zamanı {emoji1} {title} ile {reward} kazanın ve hayalinizdeki uçuşa bir adım daha yaklaşın! {emoji2}",
        "{title} fırsatıyla gökyüzüne doğru {emoji1} {reward} mil kazanarak seyahat planlarınızı şimdiden yapın! {emoji2}",
    ],
}

DEFAULT_TEMPLATES = [
    "{title} kampanyası başladı {emoji1} {reward} avantajıyla bu fırsatı değerlendirin, son güne bırakmayın! {emoji2}",
    "Kartınızla kazanmanın tam zamanı {emoji1} {title} ile {reward} fırsatını yakalayın! {emoji2}",
    "{title} fırsatı sizi bekliyor {emoji1} {reward} avantajından yararlanmak için hemen harekete geçin! {emoji2}",
]


def generate_text(title: str, reward_text: str, reward_type: str, sector_slug: str) -> str:
    """Generate marketing text from templates."""
    config = SECTOR_CONFIG.get(sector_slug, DEFAULT_CONFIG)
    emojis = config['emojis']
    
    # Pick reward type templates or default
    rtype = (reward_type or '').lower()
    templates = REWARD_TEMPLATES.get(rtype, DEFAULT_TEMPLATES)
    
    template = random.choice(templates)
    emoji1 = random.choice(emojis)
    emoji2 = random.choice([e for e in emojis if e != emoji1] or emojis)
    
    reward = reward_text or "özel avantaj"
    safe_title = title[:60] if title else "Kampanya"
    
    result = template.format(
        title=safe_title,
        reward=reward,
        emoji1=emoji1,
        emoji2=emoji2,
    )
    
    # Append a random CTA if text is short
    if len(result) < 140:
        result += " " + random.choice(config['cta'])
    
    return result


def main():
    print("🚀 Template-Based Bulk Marketing Text Güncelleyici")
    print("=" * 60)
    
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT c.id, c.title, c.reward_text, c.reward_type, c.ai_marketing_text,
                   s.slug as sector_slug
            FROM campaigns c
            LEFT JOIN sectors s ON c.sector_id = s.id
            WHERE c.is_active = true AND c.is_approved = true
            ORDER BY c.id DESC
        """)).fetchall()
        
        total = len(rows)
        print(f"📊 Toplam {total} aktif kampanya bulundu.\n")
        
        updated = 0
        skipped = 0
        
        for i, row in enumerate(rows):
            current = row.ai_marketing_text or ""
            
            # Skip if already emoji-rich and long enough
            has_emoji = any(ord(c) > 0x1F000 for c in current)
            if has_emoji and len(current) >= 120:
                skipped += 1
                continue
            
            new_text = generate_text(
                title=row.title or "",
                reward_text=row.reward_text or "",
                reward_type=row.reward_type or "",
                sector_slug=row.sector_slug or ""
            )
            
            conn.execute(
                text("UPDATE campaigns SET ai_marketing_text = :txt WHERE id = :id"),
                {"txt": new_text, "id": row.id}
            )
            updated += 1
            
            if updated % 100 == 0:
                conn.commit()
                print(f"   ✅ {updated} kampanya güncellendi...")
        
        conn.commit()
        
        print(f"\n{'=' * 60}")
        print(f"🏁 SONUÇ:")
        print(f"   ✅ Güncellenen: {updated}")
        print(f"   ⏭️  Atlanan (zaten güncel): {skipped}")
        print(f"   📊 Toplam: {total}")
        
        # Show 5 samples
        print(f"\n📝 ÖRNEK ÇIKTILAR:")
        samples = conn.execute(text("""
            SELECT id, title, ai_marketing_text FROM campaigns 
            WHERE is_active = true AND is_approved = true
            ORDER BY RANDOM() LIMIT 5
        """)).fetchall()
        for s in samples:
            print(f"   ID:{s.id} → {s.ai_marketing_text}")
            print()


if __name__ == "__main__":
    main()
