import os
import sys
from typing import List, Dict, Any
from sqlalchemy import func
from datetime import datetime

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign, Brand, CampaignBrand, Sector, Bank, Card
from src.services.ai_parser import AIParser
from sqlalchemy import text

def _get_campaign_brands(db, campaign_id: int) -> List[str]:
    brands = db.query(Brand.name).join(CampaignBrand).filter(CampaignBrand.campaign_id == campaign_id).all()
    return [b[0] for b in brands]

def _get_sector_name(db, sector_id: int) -> str:
    if not sector_id: return "None"
    sector = db.query(Sector).filter(Sector.id == sector_id).first()
    return sector.name if sector else "Bilinmiyor"

def repair_defective_campaigns(campaign_ids: List[int]):
    print(f"🛠️ Starting Targeted Repair for {len(campaign_ids)} campaigns...")
    db = SessionLocal()
    parser = AIParser()
    
    report = []
    
    for cid in campaign_ids:
        c = db.query(Campaign).get(cid)
        if not c:
            continue
            
        print(f"\n🔄 Repairing [{cid}] {c.title[:40]}...")
        
        # Save Before State
        before_state = {
            "title": c.title,
            "description": c.description,
            "reward_text": c.reward_text,
            "reward_value": c.reward_value,
            "reward_type": c.reward_type,
            "sector": _get_sector_name(db, c.sector_id),
            "brands": ", ".join(_get_campaign_brands(db, c.id)),
            "eligible_cards": c.eligible_cards,
            "participation": c.participation,
            "conditions_len": len(c.conditions) if c.conditions else 0,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "end_date": c.end_date.isoformat() if c.end_date else None
        }
        
        # Determine strict rules based on campaign context
        exclude_brands = set()
        if "Türk Telekom" in c.title or "Tivibu" in c.clean_text:
             exclude_brands.update(["Tivibu", "Muud", "Selfy"])
             
        # Call AI Parser (Gemini 3.1)
        ai_data = parser.parse_campaign_data(
            raw_text=c.clean_text,
            title=c.title,
            force=True, # Skip Cache
            campaign_id=c.id
        )
        
        if ai_data:
            # Reconstruct conditions
            conds = ai_data.get('conditions', [])
            part = ai_data.get('participation')
            if part and part != "Otomatik katılım":
                conds.insert(0, f"KATILIM: {part}")
            
            # Find new sector safely
            sector_id_new = c.sector_id
            if ai_data.get('sector'):
                 s = db.query(Sector).filter(Sector.slug == ai_data['sector']).first()
                 if s: sector_id_new = s.id
                 
            # Save After State (Simulation) 
            # In a real run, we would UPDATE the database and insert to CampaignAuditLog here
            
            # Since user wants comparison before saving blindly, we'll write it to report.
            # Usually we'd commit to DB, but for safe-verify we show it first.
            after_state = {
                "title": ai_data.get('title'),
                "description": ai_data.get('description'),
                "reward_text": ai_data.get('reward_text'),
                "reward_value": ai_data.get('reward_value'),
                "reward_type": ai_data.get('reward_type'),
                "sector": ai_data.get('sector', 'None'),
                "brands": ", ".join(ai_data.get('brands', [])),
                "eligible_cards": ", ".join(ai_data.get('cards', [])),
                "participation": ai_data.get('participation'),
                "conditions_len": len("\n".join(conds)),
                "start_date": ai_data.get('start_date'),
                "end_date": ai_data.get('end_date')
            }
            
            report.append({
                "id": c.id,
                "before": before_state,
                "after": after_state
            })
            print(f"✅ AI parsed successfully")
        else:
            print(f"❌ AI parse failed")

    # Generate Markdown Report
    report_file = os.path.join(project_root, "repair_test_report.md")
    with open(report_file, "w") as f:
        f.write("# 🛠️ AI Onarım (Repair) Öncesi/Sonrası Test Raporu\n\n")
        f.write("Bu rapor, AI'nın kusurlu kampanyaları nasıl tamir ettiğini kolon bazlı gösterir. Henüz DB'ye yazılmamıştır.\n\n")
        
        for r in report:
            f.write(f"## 📌 Kampanya ID: {r['id']} - {r['before']['title']}\n")
            f.write("| Kolon | ❌ ESKİ (Veritabanındaki) | ✅ YENİ (AI Tarafından Düzeltilen) |\n")
            f.write("|---|---|---|\n")
            
            b = r['before']
            a = r['after']
            
            for key in ["description", "reward_text", "reward_value", "reward_type", "sector", "brands", "eligible_cards", "participation", "conditions_len", "start_date", "end_date"]:
                # Highlight changes natively
                v1 = str(b[key]).replace("\n", " ") if b[key] is not None else "-"
                v2 = str(a[key]).replace("\n", " ") if a[key] is not None else "-"
                
                if v1 != v2:
                    f.write(f"| **{key}** | *{v1}* | **{v2}** |\n")
                else:
                    f.write(f"| {key} | {v1} | {v2} |\n")
            f.write("\n")
            
    print(f"\n✅ Report generated: {report_file}")
    db.close()

if __name__ == "__main__":
    # Selected 5 diverse targets from previous audit
    target_ids = [10989, 16220, 11295, 12617, 14829]
    repair_defective_campaigns(target_ids)
