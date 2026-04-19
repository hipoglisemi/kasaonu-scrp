from playwright.sync_api import sync_playwright

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://example.com")
        print(f"Title: {page.title()}")
        browser.close()
    print("✅ Playwright is working correctly.")
except Exception as e:
    print(f"❌ Playwright test failed: {e}")
