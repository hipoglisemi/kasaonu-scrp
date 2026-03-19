"""
Automated Brand Merge Script
============================
Scans the database for potential duplicate brands using fuzzy matching
and merges them into a single primary brand.
"""

import os
import sys
import logging

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import get_db_session
from src.models import Brand
from src.services.brand_matcher import _simplify
from src.services.brand_merger import merge_brands

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def run_auto_merge(dry_run=True):
    print(f"🚀 Starting Automated Brand Merge (Dry Run: {dry_run})...")
    
    with get_db_session() as db:
        brands = db.query(Brand).all()
        print(f"   📊 Analyzing {len(brands)} brands...")
        
        # Group by simplified key
        groups = {}
        for b in brands:
            key = _simplify(b.name)
            if not key: continue
            
            if key not in groups:
                groups[key] = []
            groups[key].append(b)
        
        merge_count = 0
        potential_merges = 0
        
        for key, group in groups.items():
            if len(group) > 1:
                potential_merges += 1
                # Sort brands to pick the 'best' one as target
                # Criteria: 1. Most campaigns, 2. Oldest (id or date)
                group.sort(key=lambda x: (len(x.campaigns), -len(x.name)), reverse=True)
                
                target = group[0]
                to_merge = group[1:]
                
                print(f"\n📂 Group [{key}]: Target is '{target.name}' ({target.id})")
                for source in to_merge:
                    print(f"   ⚠️ Potential Source: '{source.name}' ({source.id})")
                    
                    if not dry_run:
                        success = merge_brands(db, source.id, target.id)
                        if success:
                            merge_count += 1
                    else:
                        merge_count += 1
        
        if dry_run:
            print(f"\n✅ Dry run complete. Found {potential_merges} groups containing {merge_count} brands to be merged.")
        else:
            print(f"\n✅ Merge complete. Successfully merged {merge_count} brands into their primaries.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually apply the merges (not a dry run)")
    args = parser.parse_args()
    
    run_auto_merge(dry_run=not args.apply)
