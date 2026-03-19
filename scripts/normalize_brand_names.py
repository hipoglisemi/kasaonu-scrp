"""
Normalize Brand Names Script (v2)
=================================
Updates all brand names in the database to Title Case.
If a name collision occurs (e.g., "SUPERSTEP" becomes "Superstep" and
"Superstep" already exists), it automatically merges them.
"""

import os
import sys
import logging

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import get_db_session
from src.models import Brand
from src.services.brand_merger import merge_brands
from typing import Optional, List

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def to_title_case(name: str) -> str:
    if not name: 
        return ""
    return name.title()

def run_normalization():
    print(f"🚀 Starting Robust Brand Name Normalization...")
    
    with get_db_session() as db:
        # Refresh brands after potential previous merges
        brands = db.query(Brand).all()
        updated_count = 0
        merge_count = 0
        
        for b in brands:
            # Re-fetch or check if brand was deleted in a previous iteration's merge
            current_brand: Optional[Brand] = db.query(Brand).filter(Brand.id == b.id).first()
            if not current_brand:
                continue

            original_name: str = current_brand.name
            target_name = to_title_case(original_name)
            
            if original_name == target_name:
                continue

            # Check if target name already exists in DB (excluding itself)
            existing = db.query(Brand).filter(Brand.name == target_name).first()
            
            if existing and existing.id != current_brand.id:
                print(f"   💥 Collision: '{original_name}' -> '{target_name}' (Already exists). Merging...")
                if merge_brands(db, current_brand.id, existing.id):
                    merge_count += 1
            else:
                # No collision in DB, update name
                print(f"   🔄 '{original_name}' -> '{target_name}'")
                current_brand.name = target_name
                updated_count += 1
                db.commit() # Commit each step to keep it safe

        print(f"\n✅ Legal formatting complete. Updated {updated_count} names, performed {merge_count} merges.")

if __name__ == "__main__":
    run_normalization()
