import re
import logging
from typing import Optional, Dict, List, Tuple
from collections import Counter
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.models import PointBlankRule, Brand

logger = logging.getLogger(__name__)

# Short keyword threshold - keywords this length or shorter get extra scrutiny
_SHORT_KW_THRESHOLD = 4


class PointBlankMatcher:
    """
    Point-Blank Engine v2: Database-driven regex matching for brands and sectors.
    Prevents AI hallucinations for known merchants.
    
    v2 improvements:
    - Tighter regex: suffix only after apostrophe (prevents Etiket->Eti, Maximum->Max)
    - Title-priority: short keywords (<=4 chars) must match in title to be trusted
    - Sector coherence filter: body-only short matches from unrelated sectors are dropped
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
            logger.info(f"\U0001f3af Point-Blank Engine v2: {len(self.rules)} verified rules loaded.")
        except Exception as e:
            logger.error(f"\u274c Error loading Point-Blank rules: {e}")
            self.rules = []

    def _build_pattern(self, keyword: str) -> str:
        """
        Build regex pattern for a keyword with Turkish-aware word boundaries.
        
        v2 FIX: Suffix group now ONLY allows characters after an apostrophe.
        This prevents false positives like:
          - "Etiket" matching "Eti" (was: Eti + ket suffix captured)
          - "Maximum" matching "Max" (was: Max + imum suffix captured)
          - "Shopping" matching "Hop" (was: ...Hop + ping suffix captured — actually blocked by lookbehind)
        
        Legitimate Turkish suffixes still work: Eti'nin, Migros'un, Opet'te
        """
        kw_pattern = re.escape(keyword)
        
        # Turkish letter set for word boundary checks
        tr_letters = r"a-z\u00e7\u011f\u0131\u00f6\u015f\u00fcA-Z\u00c7\u011e\u0130\u00d6\u015e\u00dc"
        
        # v2: Only allow suffix after apostrophe ('), not bare letter continuation
        # Old: (['']?[a-zçğıöşü]*)? — matched "Etiket" as "Eti" + "ket"
        # New: (?:[''\u2019][a-zçğıöşü]+)? — only matches "Eti'nin", "Eti\u2019nin"
        pattern = (
            f"(?i)"
            f"(?<![{tr_letters}])"       # Not preceded by a letter (word boundary start)
            f"{kw_pattern}"               # The keyword itself
            f"(?:['\u2018\u2019][a-z\u00e7\u011f\u0131\u00f6\u015f\u00fc]+)?"  # Optional: apostrophe + Turkish suffix
            f"(?![{tr_letters}])"         # Not followed by a letter (word boundary end)
        )
        return pattern

    def match_campaign(self, title: str, description: Optional[str] = "") -> List[Dict]:
        """
        Match a campaign against all point-blank rules.
        Returns a list of dicts with brand, sector, rule_id, keyword, and title_match flag.
        
        v2 LOGIC:
        1. Search title and body separately
        2. Title matches are always trusted (high confidence)
        3. Body-only matches for short keywords (<=4 chars) are flagged
        4. Sector coherence filter removes suspicious body-only short matches
        """
        title_str = title or ""
        body_str = description or ""
        
        raw_matches = []
        seen_brands = set()
        
        for rule in self.rules:
            if rule.brand_name in seen_brands:
                continue
                
            pattern = self._build_pattern(rule.keyword)
            
            # Check title first, then body
            in_title = bool(re.search(pattern, title_str))
            in_body = bool(re.search(pattern, body_str)) if body_str else False
            
            if in_title or in_body:
                is_short = len(rule.keyword) <= _SHORT_KW_THRESHOLD
                
                try:
                    rule.match_count = (rule.match_count or 0) + 1
                except:
                    pass

                raw_matches.append({
                    "brand": rule.brand_name,
                    "sector": rule.sector_slug,
                    "rule_id": rule.id,
                    "keyword": rule.keyword,
                    "title_match": in_title,
                    "is_short": is_short,
                })
                if rule.brand_name:
                    seen_brands.add(rule.brand_name)
        
        # --- Sector Coherence Filter ---
        return self._filter_by_sector_coherence(raw_matches)

    def _filter_by_sector_coherence(self, raw_matches: List[Dict]) -> List[Dict]:
        """
        Filter out suspicious body-only short-keyword matches whose sector
        conflicts with the campaign's dominant sector.
        
        RULES:
        1. Title matches are ALWAYS kept (user explicitly sees brand in title)
        2. Body matches for long keywords (>4 chars) are ALWAYS kept
        3. Body-only short keywords: kept IF their sector agrees with dominant sector
        4. If NO title matches exist, the dominant sector comes from the most frequent
           sector among all matches → short keywords from minority sectors are dropped
        
        EXAMPLES:
        - "Opet'ten akaryakıt al, Migros'ta çek kazan" (both in title) → BOTH KEPT ✅
        - Giyim campaign, "Hop" only in body → Hop (ulaşım) dropped ✅ 
        - "Eti kampanyasında fırsat" (Eti in title) → KEPT ✅
        """
        if len(raw_matches) <= 1:
            return raw_matches
        
        # Separate matches by confidence
        title_matches = [m for m in raw_matches if m["title_match"]]
        trusted_body = [m for m in raw_matches if not m["title_match"] and not m["is_short"]]
        suspect_body = [m for m in raw_matches if not m["title_match"] and m["is_short"]]
        
        # If no suspect matches, nothing to filter
        if not suspect_body:
            return raw_matches
        
        # Determine dominant sector(s) from trusted matches
        trusted = title_matches + trusted_body
        if trusted:
            sector_counts = Counter(m["sector"] for m in trusted if m.get("sector"))
            dominant_sectors = set(sector_counts.keys())
        else:
            # All matches are suspect short body-only → use most common sector
            sector_counts = Counter(m["sector"] for m in raw_matches if m.get("sector"))
            if sector_counts:
                max_count = sector_counts.most_common(1)[0][1]
                dominant_sectors = {s for s, c in sector_counts.items() if c == max_count}
            else:
                dominant_sectors = set()
        
        # Filter: keep suspect body matches only if their sector is in dominant set
        filtered = list(title_matches) + list(trusted_body)
        for m in suspect_body:
            if m.get("sector") in dominant_sectors:
                filtered.append(m)
            else:
                logger.info(
                    f"\U0001f6e1\ufe0f Sector filter: dropped '{m['keyword']}' "
                    f"(sector={m['sector']}) - conflicts with dominant {dominant_sectors}"
                )
        
        return filtered

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
                logger.info(f"\U0001f195 New Point-Blank Candidate reported: {keyword} -> {brand_name}")
            elif existing.sample_campaign_id is None and campaign_id is not None:
                # Update source if it was missing
                existing.sample_campaign_id = campaign_id
                self.db.commit()
                logger.info(f"\U0001f517 Updated source for existing Point-Blank Rule: {keyword} -> Campaign {campaign_id}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"\u274c Error reporting candidate: {e}")

def get_point_blank_matcher(db: Session) -> PointBlankMatcher:
    """Helper to get a matcher instance."""
    return PointBlankMatcher(db)
