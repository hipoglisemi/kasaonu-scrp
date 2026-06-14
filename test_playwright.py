from playwright.sync_api import sync_playwright
import time
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
    page = browser.new_page()
    page.goto("https://tkpay.com/tr/all-campaigns", timeout=45000, wait_until="networkidle")
    time.sleep(2)
    links = page.query_selector_all("a")
    for link in links:
        href = link.get_attribute("href")
        print(href)
    browser.close()
