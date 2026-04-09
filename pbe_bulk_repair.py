"""
PBE Bulk Sector & Brand Repair
-------------------------------
AI çağırmadan, sadece PBE (Point-Blank Engine) kurallarıyla
tüm aktif kampanyaların sektör ve marka eşleşmelerini düzeltir.

Kullanım:
  python3 pbe_bulk_repair.py                  # Dry-run (sadece rapor)
  python3 pbe_bulk_repair.py --apply          # Değişiklikleri uygula
  python3 pbe_bulk_repair.py --apply --limit 50  # İlk 50 kampanya
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.database import SessionLocal
from src.models import Campaign, Sector, CampaignBrand, Brand
from src.services.point_blank_matcher import get_point_blank_matcher
from src.services.brand_matcher import get_or_create_brand
from src.services.ai_parser import AIParser
from sqlalchemy.orm import joinedload
import argparse

# Banka adları — marka olarak eklenmemeli
BANK_BRANDS = {
    "Yapı Kredi", "Garanti BBVA", "Garanti", "İş Bankası", "Akbank",
    "Halkbank", "QNB Finansbank", "QNB", "Vakıfbank", "TEB", "Denizbank",
    "HSBC", "ING", "Albaraka", "Ziraat", "Kuveyt Türk", "Türkiye Finans",
    "Odeabank", "Fibabanka", "Anadolubank", "Şekerbank", "Aktif Bank",
    "Yapı ve Kredi", "Türk Ekonomi Bankası", "Alternatif Bank", "Burgan Bank", "On Digital",
    "Mastercard", "Visa", "Masterpass", "TROY", "Maestro", "American Express", "AMEX"
}

_ai_parser = None

def get_ai_parser():
    global _ai_parser
    if _ai_parser is None:
        _ai_parser = AIParser()
    return _ai_parser

def run_pbe_repair(apply=False, limit=None, use_ai=False):
    db = SessionLocal()
    
    try:
        # PBE yükle
        pb_matcher = get_point_blank_matcher(db)
        
        # Tüm sektörleri sözlüğe al
        sectors = {s.slug: s for s in db.query(Sector).all()}
        
        # Aktif kampanyaları al
        query = db.query(Campaign).options(
            joinedload(Campaign.brands).joinedload(CampaignBrand.brand),
            joinedload(Campaign.sector)
        ).filter(Campaign.is_active == True)
        if limit:
            query = query.limit(limit)
        campaigns = query.all()
        
        print(f"📊 {len(campaigns)} aktif kampanya taranacak...")
        print(f"🎯 PBE: {len(pb_matcher.rules)} kural yüklü")
        print(f"{'🔧 APPLY MODE' if apply else '👁️ DRY-RUN MODE (--apply ekle uygulamak için)'}")
        print("=" * 80)
        
        sector_fixes = 0
        brand_adds = 0
        brand_removes = 0
        skipped = 0
        
        brand_cache = {}
        
        for c in campaigns:
            title = c.title or ""
            clean_text = c.clean_text or ""
            
            # PBE eşleştir - SADECE TITLE kullanarak (Footer kirliliğini engeller ve 100x hızlandırır)
            pb_matches = pb_matcher.match_campaign(title, "")
            
            # --- AI FALLBACK ---
            if not pb_matches and use_ai:
                print(f"\n🔍 PBE eşleşmedi, AI devrede: [{c.id}] {title[:50]}...")
                try:
                    ai = get_ai_parser()
                    # We pass the full text to AI
                    ai_res = ai.parse_campaign_data(
                        raw_text=c.description or "",
                        title=title,
                        bank_name=c.bank.name if c.bank else None,
                        campaign_id=c.id
                    )
                    
                    if ai_res and ai_res.get("sector") != "Diğer":
                        # Convert AI result to PBE-like format for the logic below
                        # We only take the brands if they are not generic
                        ai_brands = [b for b in ai_res.get("brands", []) if b and b != "Genel"]
                        
                        pb_matches = []
                        for b in ai_brands:
                            pb_matches.append({
                                "brand": b,
                                "sector": ai_res.get("sector_slug") or ai_res.get("sector"),
                                "source": "AI_FALLBACK"
                            })
                        
                        # If no brands found but sector is identified
                        if not pb_matches and ai_res.get("sector"):
                            pb_matches.append({
                                "brand": None,
                                "sector": ai_res.get("sector_slug") or ai_res.get("sector"),
                                "source": "AI_FALLBACK"
                            })
                except Exception as e:
                    print(f"   ⚠️ AI Parser error: {e}")

            if not pb_matches:
                skipped += 1
                continue
            
            # Sadece title'dan yakalanan markaları kaale al (artık hepsi böyle)
            # DUPLICATE PROTECTION: PBE can return the same brand match twice. Deduplicate it!
            brand_matches_raw = [m for m in pb_matches if m.get("brand") and m["sector"] != "BLACKLIST"]
            brand_matches = []
            seen_brands = set()
            for m in brand_matches_raw:
                if m["brand"] not in seen_brands:
                    seen_brands.add(m["brand"])
                    brand_matches.append(m)
            # Sektör eşleşmeleri
            sector_matches = [m for m in pb_matches if m.get("brand") and m["sector"] != "BLACKLIST" and m["sector"] != "diger"]
            
            changes = []
            
            # --- SEKTÖR DÜZELTMESİ ---
            current_slug = c.sector.slug if c.sector else "diger"
            
            if sector_matches:
                pbe_sector = sector_matches[0]["sector"]
                
                # Sadece mevcut "diger" ise veya PBE farklı spesifik sektör bulmuşsa
                if current_slug == "diger" and pbe_sector != "diger":
                    if pbe_sector in sectors:
                        if apply:
                            c.sector_id = sectors[pbe_sector].id
                        changes.append(f"Sektör: {current_slug} → {pbe_sector} (PBE: {sector_matches[0]['brand']})")
                        sector_fixes += 1
            
            # --- MARKA DÜZELTMESİ ---
            existing_brands = {cb.brand.name: cb.brand for cb in c.brands if cb.brand}
            
            # 1. Banka adlarını kaldır
            for b_name, b_obj in existing_brands.items():
                if b_name in BANK_BRANDS:
                    if apply:
                        db.query(CampaignBrand).filter(
                            CampaignBrand.campaign_id == c.id,
                            CampaignBrand.brand_id == b_obj.id
                        ).delete()
                    changes.append(f"Marka kaldırıldı: {b_name} (banka adı)")
                    brand_removes += 1
            
            # 2. PBE markalarını ekle (yoksa)
            for m in brand_matches:
                b_name = m["brand"]
                if b_name in BANK_BRANDS:
                    continue
                
                if apply:
                    # Markanın veritabanındaki asıl karşılığını bul (alias çözümü dahil)
                    brand = get_or_create_brand(db, b_name, brand_cache)
                    if brand and brand.name not in existing_brands:
                        existing_brands[brand.name] = brand  # Aynı kampanyada tekrar eklememek için önbelleğe al
                        # Zaten eklenmemiş mi db'den de teyit et
                        exists = db.query(CampaignBrand).filter(
                            CampaignBrand.campaign_id == c.id,
                            CampaignBrand.brand_id == brand.id
                        ).first()
                        if not exists:
                            db.add(CampaignBrand(campaign_id=c.id, brand_id=brand.id))
                        changes.append(f"Marka eklendi: {brand.name} ({m['sector']})")
                        brand_adds += 1
                else:
                    # Dry-run
                    if b_name not in existing_brands:
                        existing_brands[b_name] = None
                        changes.append(f"Marka eklendi: {b_name} ({m['sector']})")
                        brand_adds += 1
            
            if changes:
                print(f"\n[{c.id}] {title[:60]}...")
                for ch in changes:
                    print(f"   {'✅' if apply else '📋'} {ch}")
                
                if apply:
                    db.flush()
        
        if apply:
            db.commit()
        
        print("\n" + "=" * 80)
        print(f"📊 SONUÇ {'(UYGULANDI)' if apply else '(DRY-RUN)'}")
        print(f"   Sektör düzeltme: {sector_fixes}")
        print(f"   Marka ekleme:    {brand_adds}")
        print(f"   Marka kaldırma:  {brand_removes}")
        print(f"   PBE eşleşme yok: {skipped}")
        print(f"   Toplam taranan:  {len(campaigns)}")
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Değişiklikleri uygula (varsayılan: dry-run)")
    parser.add_argument("--limit", type=int, help="Kaç kampanya taransın")
    parser.add_argument("--ai", action="store_true", help="PBE eşleşmezse AI fallback kullan")
    args = parser.parse_args()
    
    run_pbe_repair(apply=args.apply, limit=args.limit, use_ai=args.ai)
