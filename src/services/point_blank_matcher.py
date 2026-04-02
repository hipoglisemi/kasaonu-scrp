import re
import logging
from typing import Optional, Dict, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.models import PointBlankRule, Brand

logger = logging.getLogger(__name__)

class PointBlankMatcher:
    """
    Point-Blank Engine: Database-driven regex matching for brands and sectors.
    Prevents AI hallucinations for known merchants.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.rules = []
        self._load_rules()

    def _load_rules(self):
        """Load and cache verified rules from DB for high performance."""
        try:
            self.rules = self.db.query(PointBlankRule).filter(
                PointBlankRule.is_verified == True
            ).all()
            logger.info(f"🎯 Point-Blank Engine: {len(self.rules)} verified rules loaded.")
        except Exception as e:
            logger.error(f"❌ Error loading Point-Blank rules: {e}")
            self.rules = []

    def match_campaign(self, title: str, description: Optional[str] = "") -> List[Dict]:
        """
        Match a campaign against all point-blank rules.
        Returns a list of dicts with brand, sector, rule_id, and keyword.
        Deduplicates by brand_name to avoid redundant tags.
        """
        full_text = f"{title} {description if description else ''}"
        matches = []
        seen_brands = set()
        
        for rule in self.rules:
            # Flexible regex for Turkish apostrophes and suffixes
            pattern = f"(?i)\\b{re.escape(rule.keyword)}(['’]?[a-zçğıöşü]*)?\\b"
            
            if re.search(pattern, full_text):
                if rule.brand_name not in seen_brands:
                    try:
                        rule.match_count += 1
                    except:
                        pass

                    matches.append({
                        "brand": rule.brand_name,
                        "sector": rule.sector_slug,
                        "rule_id": rule.id,
                        "keyword": rule.keyword
                    })
                    if rule.brand_name:
                        seen_brands.add(rule.brand_name)
        
        return matches

    def report_new_candidate(self, keyword: str, brand_name: Optional[str], sector_slug: Optional[str], campaign_id: Optional[int] = None):
        """
        Log a new candidate discovered by AI for admin review.
        """
        if not keyword or len(keyword) < 3:
            return
            
        try:
            # Check if exists (any status)
            existing = self.db.query(PointBlankRule).filter(
                PointBlankRule.keyword.ilike(keyword)
            ).first()
            
            if not existing:
                new_rule = PointBlankRule(
                    keyword=keyword,
                    brand_name=brand_name if brand_name else None,
                    sector_slug=sector_slug if sector_slug else "diger",
                    is_verified=False,
                    sample_campaign_id=campaign_id,
                    match_count=0
                )
                self.db.add(new_rule)
                self.db.commit()
                logger.info(f"🆕 New Point-Blank Candidate reported: {keyword} -> {brand_name}")
            elif existing.sample_campaign_id is None and campaign_id is not None:
                # Update source if it was missing
                existing.sample_campaign_id = campaign_id
                self.db.commit()
                logger.info(f"🔗 Updated source for existing Point-Blank Rule: {keyword} -> Campaign {campaign_id}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Error reporting candidate: {e}")

def get_point_blank_matcher(db: Session) -> PointBlankMatcher:
    """Helper to get a matcher instance."""
    return PointBlankMatcher(db)
