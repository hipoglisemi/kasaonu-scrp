import os
import time
import argparse
import re
from src.database import SessionLocal
from src.models import Campaign
from sqlalchemy import text as sql_text
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument("--window-size=1920,1080")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    stealth(driver,
        languages=["tr-TR", "tr"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver

def rescue_campaign_text(campaign_id=None, limit=50, specific_bank=None):
    db = SessionLocal()
    
    query = db.query(Campaign)
    if campaign_id:
        query = query.filter(Campaign.id == campaign_id)
    elif specific_bank:
        query = query.filter(Campaign.tracking_url.contains(specific_bank))
    else:
        query = query.filter(Campaign.clean_text.isnot(None)).filter(sql_text("length(clean_text) < 500")).limit(limit)
        
    campaigns = query.all()
    print(f"📦 Found {len(campaigns)} campaigns to rescue.")
    
    if not campaigns:
        db.close()
        return

    driver = setup_driver()

    try:
        for c in campaigns:
            print(f"🔍 Rescuing ID {c.id}: {c.title}")
            print(f"   URL: {c.tracking_url}")
            
            try:
                driver.get(c.tracking_url)
                time.sleep(5)
                
                # Scroll to load dynamic content
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(2)
                
                # Extraction logic
                text_content = ""
                if "denizbonus" in c.tracking_url or "denizbank" in c.tracking_url:
                    parts = []
                    try:
                        detail = driver.find_element("css selector", ".campaign-detail")
                        if detail: parts.append(detail.text)
                    except: pass
                    
                    try:
                        detail_text = driver.find_element("css selector", ".campaign-detail-text")
                        if detail_text: parts.append("\nKAMPANYA KOŞULLARI:\n" + detail_text.text)
                    except: pass
                    
                    try:
                        sidebar = driver.find_element("css selector", ".campaign-sidebar")
                        if sidebar: parts.append("\nEK BİLGİLER / TARİH:\n" + sidebar.text)
                    except: pass
                    
                    text_content = "\n\n---\n\n".join(parts)
                else:
                    text_content = driver.find_element("tag name", "body").text

                if text_content and len(text_content.strip()) > 100:
                    c.clean_text = text_content.strip()
                    db.commit()
                    print(f"   ✅ Saved! New length: {len(c.clean_text)}")
                else:
                    print(f"   ⚠️ Could not extract meaningful text.")
                    
            except Exception as e:
                print(f"   ❌ Error processing URL: {e}")
                
    finally:
        driver.quit()
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Rescue truncated campaign texts via Selenium')
    parser.add_argument('--id', type=int, help='Specific campaign ID')
    parser.add_argument('--bank', type=str, help='Bank keyword in URL')
    parser.add_argument('--limit', type=int, default=50, help='Limit for batch rescue')
    
    args = parser.parse_args()
    rescue_campaign_text(campaign_id=args.id, limit=args.limit, specific_bank=args.bank)
