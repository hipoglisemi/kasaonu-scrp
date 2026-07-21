from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        def log_request(route, request):
            if "api" in request.url or "json" in request.url or "campaign" in request.url:
                print(f"Intercepted API Call: {request.url}")
            route.continue_()
            
        page.route("**/*", log_request)

        print("Navigating to oliz.com.tr/kampanyalar...")
        page.goto("https://www.oliz.com.tr/kampanyalar")
        page.wait_for_load_state("networkidle")
        
        print("Page title:", page.title())
        browser.close()

if __name__ == "__main__":
    run()
