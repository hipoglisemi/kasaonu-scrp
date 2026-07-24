import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page()
        
        await page.goto('https://hopi.com.tr/kampanya/gallery-crystal-magazalarinda-tum-indirimlere-ek-750-tl-daha-az-ode/1673238', wait_until='domcontentloaded')
        await page.wait_for_timeout(2000)
        
        inner_text = await page.evaluate('''() => {
            const container = document.querySelector('.campaign-detail');
            return container ? container.innerText.trim() : 'NO CONTAINER';
        }''')
        
        print("--- EXTRACTED TEXT FROM .campaign-detail ---")
        print(inner_text)
        
        await b.close()

asyncio.run(main())
