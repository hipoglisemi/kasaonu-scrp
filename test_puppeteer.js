const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();
  await page.goto('https://tkpay.com/tr/all-campaigns', { waitUntil: 'networkidle0' });
  const links = await page.$$eval('a', as => as.map(a => a.href));
  console.log(links.filter(l => l.includes('kampanya')));
  await browser.close();
})();
