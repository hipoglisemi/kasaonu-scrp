from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome", args=["--no-sandbox", "--disable-setuid-sandbox"])
    page = browser.new_page()
    page.goto("https://tkpay.com/tr/all-campaigns", timeout=45000, wait_until="domcontentloaded")
    time.sleep(3)
    
    # Try infinite scroll 10 times
    for i in range(15):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        # Try to find and click any button that has 'Daha'
        btns = page.query_selector_all("button")
        for btn in btns:
            text = btn.inner_text()
            if text and 'Daha' in text:
                print("Clicking:", text)
                btn.click()
                time.sleep(1)
            
    time.sleep(2)
    links = page.query_selector_all("a")
    seen = set()
    for link in links:
        href = link.get_attribute("href")
        if href and ('kampanya' in href.lower() or 'campaign' in href.lower()) and href != "/tr/all-campaigns":
            seen.add(href)
            
    print(f"Total campaigns found: {len(seen)}")
    browser.close()
