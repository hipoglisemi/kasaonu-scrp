import asyncio
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

def test_maximum_scrape(url):
    print(f"Scraping {url}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"]
        )
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
        page.wait_for_timeout(1000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)
        
        html_content = page.content()
        soup = BeautifulSoup(html_content, "html.parser")
        
        selectors = [".campaign-detail", ".campaignDetail", ".content", ".detail-content", ".editor-content"]
        desc_el = soup.select_one(", ".join(selectors))
        
        if desc_el:
            print(f"✅ Found description using selector!")
            # Get text mimicking the scraper logic
            for br in desc_el.find_all("br"):
                br.replace_with("\n")
            lines = [l.strip() for l in desc_el.get_text().split("\n") if len(l.strip()) > 0]
            print("\n----- EXTRACTED TEXT -----")
            print("\n".join(lines))
            print("--------------------------")
        else:
            print(f"❌ Could not find description using selectors: {selectors}")
            print("Trying to find the main content div manually...")
            # Let's print out the classes of some div elements to guess
            for div in soup.find_all("div", limit=20):
                if div.get("class"):
                    pass # print(f"Div class: {div.get('class')}")
                    
            print("\nFallback full text snippet (first 1000 chars):")
            print(soup.get_text()[:1000].strip())

        browser.close()

if __name__ == "__main__":
    # Test with a known active URL, or fallback to campaigns listing page to find one
    # If the URL is dead, this will test the 404 handler basically.
    test_maximum_scrape("https://www.maximum.com.tr/kampanyalar/giyim-ve-aksesuar-alisverislerinize-maxipuan-firsati")
