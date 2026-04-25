const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ headless: "new", args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const page = await browser.newPage();
  
  const logs = [];
  const requests = [];

  page.on('console', msg => logs.push(`[Console ${msg.type()}] ${msg.text()}`));
  page.on('pageerror', err => logs.push(`[PageError] ${err.toString()}`));

  page.on('response', async (res) => {
    const req = res.request();
    let size = "unknown";
    try {
      const buffer = await res.buffer();
      size = buffer.length;
    } catch(e) {}
    
    requests.push({
      url: req.url(),
      method: req.method(),
      status: res.status(),
      size: size,
      ok: res.ok()
    });

    if (req.url().includes('api.ebird.org') || req.url().includes('movebank.org')) {
      if (!requests.firstApiBody) {
        try {
          const text = await res.text();
          requests.firstApiBody = `Response from ${req.url()}:\n${text}`;
        } catch(e) {}
      }
    }
  });

  await page.goto('http://localhost:3000/migration', { waitUntil: 'domcontentloaded', timeout: 60000 });

  // Wait for 10 seconds to let things settle and data fetch
  await new Promise(r => setTimeout(r, 10000));

  console.log("--- BROWSER CONSOLE ---");
  console.log(logs.join('\n'));

  console.log("\n--- DECKGL SNIPPET OUTPUT ---");
  const snippetResult = await page.evaluate(() => {
    const deck = document.querySelector('canvas');
    let out = 'Canvas present: ' + !!deck + '\n';
    const keys = Object.keys(deck || {}).filter(k => k.startsWith('__react'));
    if (keys.length) {
      const fiber = deck[keys[0]];
      out += 'DeckGL fiber found: ' + !!fiber;
    } else {
      out += 'DeckGL fiber found: false';
    }
    return out;
  });
  console.log(snippetResult);

  console.log("\n--- NETWORK TAB ---");
  requests.forEach(r => {
    console.log(`${r.method} ${r.status} ${r.url} - Size: ${r.size} bytes`);
  });

  if (requests.firstApiBody) {
    console.log("\n--- FIRST API RESPONSE ---");
    console.log(requests.firstApiBody);
  }

  await browser.close();
})();
