import traceback
import json
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

# Lazy import to avoid circular dependencies
def _get_scraper_log_model():
    try:
        from src.models import ScraperLog
    except ImportError:
        from models import ScraperLog
    return ScraperLog

def log_scraper_execution(
    db: Session,
    scraper_name: str,
    status: str,
    total_found: int = 0,
    total_saved: int = 0,
    total_skipped: int = 0,
    total_failed: int = 0,
    total_revived: int = 0,
    error_details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Saves a scraper execution log to the database.
    
    Args:
        db: SQLAlchemy DB Session
        scraper_name: Name of the scraper (e.g., 'paraf', 'masterpass')
        status: 'SUCCESS', 'FAILED', or 'PARTIAL'
        total_found: Total campaigns discovered
        total_saved: Total campaigns successfully saved/updated
        total_skipped: Total campaigns skipped (e.g., already exists)
        total_failed: Total campaigns that threw an error during scraping/parsing
        total_revived: Total passive campaigns that were revived
        error_details: Optional dictionary containing error messages or stack traces
    """
    try:
        ScraperLog = _get_scraper_log_model()
        
        # Ensure error_log is serializable JSON
        error_log_json = None
        if error_details:
            try:
                error_log_json = json.loads(json.dumps(error_details, default=str))
            except Exception:
                error_log_json = {"raw_error": str(error_details)}

        log_entry = ScraperLog(
            scraper_name=scraper_name,
            status=status,
            total_found=total_found,
            total_saved=total_saved,
            total_skipped=total_skipped,
            total_failed=total_failed,
            total_revived=total_revived,
            error_log=error_log_json,
            created_at=datetime.utcnow()
        )
        
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"⚠️ Failed to save scraper log: {e}")
        try:
            db.rollback()
        except:
            pass
