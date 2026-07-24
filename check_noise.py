import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page()
        
        await page.goto('https://hopi.com.tr/kampanya/gallery-crystal-magazalarinda-tum-indirimlere-ek-750-tl-daha-az-ode/1673238', wait_until='domcontentloaded')
        await page.wait_for_timeout(2000)
        
        inner_text = await page.evaluate('''() => {
            const noise = ['nav', 'footer', 'header', '.navbar', '.footer', '.site-footer', '.cookie-policy', '#onetrust-consent-sdk', '.bottom-menu'];
            noise.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => el.remove());
            });
            return document.body.innerText.trim();
        }''')
        
        print("--- EXTRACTED TEXT ---")
        print(inner_text)
        
        await b.close()

asyncio.run(main())
