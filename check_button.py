import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page()
        
        await page.goto('https://hopi.com.tr/kampanya/gallery-crystal-magazalarinda-tum-indirimlere-ek-750-tl-daha-az-ode/1673238', wait_until='domcontentloaded')
        await page.wait_for_timeout(2000)
        
        button_text = await page.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll('a, button'));
            for (let b of btns) {
                const text = b.innerText.trim();
                if (text === "HOPİ'Nİ KULLAN" || text === "TEKLİF KODUNU AL" || text === "KAMPANYADAN FAYDALAN") {
                    return text;
                }
            }
            return null;
        }''')
        
        print(f"Button Text found by exact match: {button_text}")
        
        # Or let's just get the largest button at the bottom
        all_buttons = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('button, a')).map(b => b.innerText.trim()).filter(t => t.length > 5);
        }''')
        print(f"All buttons: {all_buttons}")
        
        await b.close()

asyncio.run(main())
