import os
import sys
import re
from typing import List, Dict, Any
from sqlalchemy import func

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign, Brand, CampaignBrand, Sector, Bank, Card, PointBlankRule
from src.services.point_blank_matcher import get_point_blank_matcher

def audit_campaigns(sample_count: int = 100):
    print(f"🧐 Starting Smart Auditor (100 Random Campaigns)...")
    db = SessionLocal()
    matcher = get_point_blank_matcher(db)
    
    # 1. Fetch 100 random active campaigns
    campaigns = db.query(Campaign).filter(
        Campaign.is_active == True,
        Campaign.clean_text != None
    ).order_by(func.random()).limit(sample_count).all()
    
    sectors = {s.id: s.name for s in db.query(Sector).all()}
    
    report = []
    defects_found = 0
    
    for c in campaigns:
        issues = []
        
        # --- Rule 1: Point-Blank Sector/Brand Mismatch ---
        pbe_matches = matcher.match_campaign(c.title, c.clean_text)
        pbe_brands = set(m['brand'] for m in pbe_matches if m.get('brand'))
        pbe_sectors = set(m['sector'] for m in pbe_matches if m.get('sector'))
        
        # Check Brand consistency
        current_brands = db.query(Brand.name).join(CampaignBrand).filter(CampaignBrand.campaign_id == c.id).all()
        current_brands = set(b[0] for b in current_brands)
        
        missing_brands = pbe_brands - current_brands
        if missing_brands:
            issues.append(f"Markalar Eksik: {', '.join(missing_brands)} (PBE tespit etti)")
            
        # Check Sector consistency
        current_sector_slug = db.query(Sector.slug).filter(Sector.id == c.sector_id).scalar()
        if pbe_sectors and current_sector_slug and current_sector_slug not in pbe_sectors:
            if current_sector_slug != 'diger': # Ignore if already other, but flag if it contradicts
                issues.append(f"Sektör Çelişkisi: DB={current_sector_slug}, PBE={pbe_sectors}")
        elif not current_sector_slug or current_sector_slug == 'diger':
            if pbe_sectors:
                 issues.append(f"Sektör Boş/Diğer: PBE {pbe_sectors} buldu")

        # --- Rule 2: Structural Collapse (Conditions logic) ---
        clean_len = len(c.clean_text) if c.clean_text else 0
        cond_len = len(c.conditions) if c.conditions else 0
        if clean_len > 800 and cond_len < 100:
            issues.append(f"Şartlar Çok Kısa: Ham Metin {clean_len} kar, Şartlar {cond_len} kar.")

        # --- Rule 3: Reward Integrity (Basic Regex) ---
        if not c.reward_text or len(c.reward_text) < 3:
            issues.append("Ödül Metni Eksik/Çok Kısa")
        elif c.reward_value:
            # Check if value exists in clean_text
            val_str = str(int(c.reward_value))
            if val_str not in (c.clean_text or "") and val_str not in (c.title or ""):
                issues.append(f"Ödül Değeri Tutarsız: DB={val_str}, Metinde geçmiyor")

        # --- Rule 4: Eligible Cards / Participation ---
        if not c.eligible_cards or c.eligible_cards in ["-", "Any", "None"]:
            issues.append("Geçerli Kartlar Bilgisi Eksik")
        elif "Turkcell Turkcell" in c.eligible_cards or "Telekom Telekom" in c.eligible_cards:
             issues.append("Geçerli Kartlar Gürültülü (Tekrar eden isimler)")

        if not c.participation or len(c.participation) < 15:
             if "SMS" in (c.clean_text or "").upper() or "UYGULAMA" in (c.clean_text or "").upper():
                 issues.append("Katılım Şekli Muhtemelen Eksik (Metinde SMS/Uygulama geçiyor)")

        if issues:
            defects_found += 1
            bank = db.query(Bank).join(Card).filter(Card.id == c.card_id).first()
            report.append({
                "id": c.id,
                "bank": bank.name if bank else "Bilinmiyor",
                "title": c.title,
                "issues": issues
            })

    # --- Generate Report ---
    print(f"\n📊 Audit Finished. {defects_found}/{len(campaigns)} campaigns flagged with issues.")
    
    report_file = os.path.join(project_root, "audit_report_100.md")
    with open(report_file, "w") as f:
        f.write("# 🧐 Akıllı Denetçi (Auditor) Dry-Run Raporu\n\n")
        f.write(f"**Tarih:** 2026-04-09 | **Kapsam:** {len(campaigns)} Rastgele Kampanya\n")
        f.write(f"**Tespit Edilen Kusurlu Kampanya:** {defects_found}\n\n")
        f.write("| ID | Banka | Kampanya Başlığı | Tespit Edilen Şüpheli Durumlar |\n")
        f.write("|---|---|---|---|\n")
        for r in report:
            issues_str = "<br>".join([f"• {i}" for i in r['issues']])
            f.write(f"| {r['id']} | {r['bank']} | {r['title'][:60]}... | {issues_str} |\n")
            
    print(f"✅ Report generated: {report_file}")
    db.close()

if __name__ == "__main__":
    audit_campaigns(100)
