// usage: node scripts/bake/bake.mjs  → public/tex/signs.webp + src/city/signs-atlas.json
import { chromium } from 'playwright-core';
import http from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { extname, join, resolve } from 'node:path';
import os from 'node:os';
import { existsSync } from 'node:fs';

const root = resolve(new URL('../..', import.meta.url).pathname);
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.woff': 'font/woff' };
const server = http.createServer(async (req, res) => {
  try {
    const p = join(root, decodeURIComponent(req.url.split('?')[0]));
    const body = await readFile(p);
    res.writeHead(200, { 'content-type': types[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end();
  }
});
await new Promise((r) => server.listen(5299, '127.0.0.1', r));

// a Chrome or Chromium binary: CHROME_PATH, else Playwright's cached Chromium for Testing on macOS, else whatever
// `npx playwright-core install chromium` put in place
const macCft = join(os.homedir(), 'Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing');
const exe = process.env.CHROME_PATH || (existsSync(macCft) ? macCft : undefined);
const browser = await chromium.launch({ executablePath: exe });
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
page.on('pageerror', (e) => console.error('pageerror', e.message));
await page.goto('http://127.0.0.1:5299/scripts/bake/signs.html');
await page.waitForFunction(() => window.__done, null, { timeout: 120000 });
const { url, cells } = await page.evaluate(() => ({ url: document.getElementById('c').toDataURL('image/png'), cells: window.__cells }));
const png = join(root, 'assets_src/signs.png');
await writeFile(png, Buffer.from(url.split(',')[1], 'base64'));
execFileSync('magick', [png, '-quality', '92', '-define', 'webp:alpha-quality=100', join(root, 'public/tex/signs.webp')]);
await writeFile(join(root, 'src/city/signs-atlas.json'), JSON.stringify(cells));
console.log('baked', cells.length, 'signs');
await browser.close();
server.close();
