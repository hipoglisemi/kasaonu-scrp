import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import func
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# Setup paths and environment
sys.path.append("/Users/hipoglisemi/Desktop/kartavantaj-scraper")
load_dotenv("/Users/hipoglisemi/Desktop/kartavantaj-scraper/.env")

from src.database import get_db
from src.models import Campaign, Card, Bank
from src.services.ai_parser import parse_api_campaign

def fetch_detail_page(url: str) -> str:
    """Fetch detail page HTML using Playwright Firefox with fast domcontentloaded."""
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # Go to URL and wait for domcontentloaded
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            # Scroll to trigger lazy loading
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"      ⚠️ Playwright fetch failed for {url}: {e}")
        return ""

def main():
    db = next(get_db())
    
    # Find all active Yapı Kredi campaigns with short clean_text (< 600 chars)
    short_campaigns = db.query(Campaign).join(Campaign.card).join(Card.bank).filter(
        Bank.slug == "yapi-kredi",
        Campaign.is_active == True,
        (Campaign.clean_text == None) | (func.length(Campaign.clean_text) < 600)
    ).all()
    
    total_short = len(short_campaigns)
    print(f"🔍 Found {total_short} active Yapı Kredi campaigns with short/incomplete text (<600 chars).")
    
    if total_short == 0:
        print("Everything is fully enriched! No short campaigns found.")
        return
        
    print("🚀 Starting enrichment process...")
    success_count = 0
    
    for idx, c in enumerate(short_campaigns, 1):
        print(f"\n[{idx}/{total_short}] Processing Campaign #{c.id}: '{c.title[:45]}...'")
        print(f"   URL: {c.tracking_url}")
        
        # 1. Fetch full HTML content
        html_content = fetch_detail_page(c.tracking_url)
        if not html_content or len(html_content) < 2000:
            print("   ❌ Skip: Could not fetch detail page content.")
            continue
            
        # 2. Extract og:title or H1 from soup
        soup = BeautifulSoup(html_content, "html.parser")
        h1_element = soup.find('h1')
        og_title = h1_element.get_text().strip() if h1_element else None
        
        combined_content = f"--- API DATA ---\n{c.description or ''}\n\n--- DETAIL PAGE ---\n{html_content}"
        
        # 3. Re-run AI Parser on the complete text
        print("   🧠 Running Golden AI Parser on enriched content...")
        try:
            # We force it to re-parse (not hit cached short descriptions)
            ai_result = parse_api_campaign(
                title=c.title,
                short_description=c.description or '',
                content_html=combined_content,
                bank_name="Yapı Kredi",
                scraper_sector=None,
                tracking_url=c.tracking_url,
                og_title=og_title,
                force=True
            )
            
            new_clean_text = ai_result.get('_clean_text', '')
            new_cards = ", ".join(ai_result.get('cards', [])) if ai_result.get('cards') else None
            new_conditions = "\n".join(ai_result.get('conditions', []))
            
            # Print differences
            print(f"   📊 Text Length: {len(c.clean_text or '')} chars -> {len(new_clean_text)} chars")
            print(f"   💳 Cards: '{c.eligible_cards}' -> '{new_cards}'")
            
            # 4. Update Database Record
            c.clean_text = new_clean_text
            c.eligible_cards = new_cards
            c.conditions = new_conditions
            c.is_audited = False  # Reset audit flag so they can be re-audited with full content
            c.updated_at = datetime.utcnow()
            
            db.commit()
            print("   ✅ SUCCESS: Campaign fully enriched in DB!")
            success_count += 1
            
        except Exception as ae:
            db.rollback()
            print(f"   ❌ AI Parsing or DB commit error: {ae}")
            
        # Small breath to prevent hammering
        time.sleep(1)
        
    print(f"\n🎉 ENRICHMENT COMPLETE: Successfully enriched {success_count}/{total_short} Yapı Kredi campaigns!")

if __name__ == "__main__":
    main()
