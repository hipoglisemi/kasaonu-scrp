import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('https://hopi.com.tr/kampanyalar?page=1')
        await page.wait_for_selector('a[href^="/kampanya/"]')
        
        items = await page.evaluate("""
            () => {
                const links = document.querySelectorAll('a[href^="/kampanya/"]');
                return Array.from(links).map(a => {
                    const img = a.querySelector('img');
                    return {
                        url: a.href,
                        img: img ? img.src : null,
                        title: a.innerText.trim()
                    };
                }).filter(x => x.img && x.title);
            }
        """)
        
        for item in items[:10]:
            print(f"Title: {item['title'][:30]}")
            print(f"Listing IMG: {item['img']}")
            print("---")
            
        await browser.close()

asyncio.run(main())
