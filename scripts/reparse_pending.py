import os
import sys
from datetime import datetime

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign, Card, Bank
from src.services.ai_parser import parse_api_campaign
import requests
from bs4 import BeautifulSoup

def reparse_campaigns():
    db = SessionLocal()
    pending = db.query(Campaign).filter(Campaign.is_approved == False).all()
    print(f"Found {len(pending)} pending campaigns to re-parse.")

    for camp in pending:
        bank_name = camp.card.bank.name if camp.card and camp.card.bank else "Genel"
        print(f"\n[{camp.id}] Reparsing: {camp.title} ({bank_name})")
        
        url = camp.tracking_url
        if not url:
            print(f"   ⚠️ No URL for {camp.id}, skipping.")
            continue

        try:
            # For Yapı Kredi, we need to re-fetch because the saved clean_text is garbage
            # For Akbank, clean_text is empty, so we MUST re-fetch
            print(f"   🌐 Fetching fresh content from {url}...")
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            html_content = resp.text
            
            # Use bank-specific detail selectors to reduce noise at source
            soup = BeautifulSoup(html_content, 'html.parser')

            # Use Browser Mode for JavaScript/Accordion heavy sites
            use_browser = any(domain in url for domain in ["worldcard.com.tr", "turktelekom", "vodafone"])

            if use_browser:
                from playwright.sync_api import sync_playwright
                print(f"   🌐 Fetching via Browser (Firefox) + Auto-Click Accordions...")
                with sync_playwright() as p:
                    browser = p.firefox.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, wait_until="networkidle", timeout=30000)

                    # 1. Scroll to load lazy content
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    import time
                    time.sleep(2)

                    # 2. Click Accordions (TT / Vodafone style)
                    try:
                        # Find all potential clickable headers
                        headers = page.query_selector_all('.accordion-header, .accordion-title, h3.accordion-title')
                        for h in headers:
                            try:
                                if h.is_visible():
                                    h.click()
                                    time.sleep(0.5)
                            except: pass
                    except: pass

                    # 3. Smart Wait & Content Capture
                    try:
                        page.wait_for_selector(".campaign-terms, .campaign-detail-tab-details, .campaign-detail-content, .campaign-detail-box, .accordion-content", timeout=5000)
                    except: pass

                    browser_html = page.content()
                    inner_soup = BeautifulSoup(browser_html, 'html.parser')
                    main = inner_soup.select_one('.campaign-terms, .campaign-detail-tab-details, .campaign-detail-content, .campaign-detail, .campaign-detail-box, .accordion-content, main')
                    html_content = str(main) if main else browser_html
                    browser.close()
            elif "akbank.com" in url:
                main = soup.select_one('.campaign-detail, .content-area, main')
                html_content = str(main) if main else html_content

            # Title extraction tweaks for TT
            if "turktelekom" in url:
                h1 = soup.select_one("h1.campaign-detail-title, .campaign-detail-info h1, h1")
                if h1 and len(h1.get_text(strip=True)) > 5:
                    camp.title = h1.get_text(strip=True)
                    print(f"   🏷️ Fixed Title: {camp.title}")

            # Re-parse with NEW AIParser rules
            print(f"   🧠 Sending to AI (Bank: {bank_name})...")
            ai_data = parse_api_campaign(
                title=camp.title,
                short_description=camp.description or "",
                content_html=html_content,
                bank_name=bank_name,
                tracking_url=url,
                force=True # Bypass cache to use new rules
            )
            
            if ai_data and not ai_data.get("_ai_failed"):
                # Update Campaign
                camp.participation = ai_data.get('participation')
                camp.eligible_cards = ", ".join(ai_data.get('cards', [])) if ai_data.get('cards') else None
                camp.conditions = "\n".join(ai_data.get('conditions', [])) if isinstance(ai_data.get('conditions'), list) else ai_data.get('conditions')
                camp.clean_text = ai_data.get('_clean_text')
                # Fixed title from AI if our local extract was bad
                if ai_data.get('short_title'):
                    camp.title = ai_data.get('short_title')
                
                print(f"   ✅ Done! (Part: {camp.participation[:30]}..., Cards: {camp.eligible_cards})")
            else:
                print(f"   ❌ AI Parse failed for {camp.id}")

            db.commit()
        except Exception as e:
            print(f"   ❌ Error reparsing {camp.id}: {e}")
            db.rollback()

    db.close()

if __name__ == "__main__":
    reparse_campaigns()
