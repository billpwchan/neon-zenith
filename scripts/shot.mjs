// Headed screenshots and frame-time stats at the real display setup (1920x1080 @2x by default).
// usage: node scripts/shot.mjs '{"url":"http://127.0.0.1:5200/","views":[{"q":"cam=...","name":"a.png","wait":4,"measure":3}]}'
import { chromium } from 'playwright-core';
import { mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import os from 'node:os';

const cfg = JSON.parse(process.argv[2] || '{}');
const out = cfg.out || join(process.cwd(), '.cache', 'shots');
mkdirSync(out, { recursive: true });
// a Chrome or Chromium binary: CHROME_PATH, else Playwright's cached Chromium for Testing on macOS, else whatever
// `npx playwright-core install chromium` put in place
const macCft = join(os.homedir(), 'Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing');
const exe = process.env.CHROME_PATH || (existsSync(macCft) ? macCft : undefined);
const W = cfg.w || 1920, H = cfg.h || 1080;
const browser = await chromium.launch({
  headless: false,
  executablePath: exe,
  args: ['--enable-unsafe-webgpu', '--ignore-gpu-blocklist', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows', `--window-size=${W},${H + 90}`, '--autoplay-policy=no-user-gesture-required'],
});
const hardStop = setTimeout(() => { try { browser.process()?.kill('SIGKILL'); } catch {} console.log(JSON.stringify({ error: 'timeout', logs })); process.exit(2); }, (cfg.timeout || 240) * 1000);
process.on('uncaughtException', (e) => { try { browser.process()?.kill('SIGKILL'); } catch {} console.log(JSON.stringify({ error: String(e), logs })); process.exit(1); });
process.on('unhandledRejection', (e) => { try { browser.process()?.kill('SIGKILL'); } catch {} console.log(JSON.stringify({ error: String(e), logs })); process.exit(1); });
const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: cfg.dpr || 2, hasTouch: !!cfg.touch, isMobile: !!cfg.touch });
const page = await ctx.newPage();
const logs = [];
page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) logs.push(`${m.type()}: ${m.text()}`.slice(0, 500)); });
page.on('crash', () => logs.push('page crashed'));
page.on('pageerror', (e) => logs.push('pageerror: ' + e.message + ' @ ' + (e.stack || '').split('\n').slice(1, 4).map((l) => l.trim()).join(' | ')));

const measure = (sec) => page.evaluate(async (sec) => {
  const nz = window.__nz;
  const info = nz?.renderer?.info;
  // info resets on every render() by default (post passes included), so count whole frames by hand: exactly one
  // app frame runs between two of these callbacks
  const auto = info && info.autoReset;
  if (info) { info.autoReset = false; info.reset(); }
  const t = [], draws = [], tris = []; let last = performance.now(); const end = last + sec * 1000;
  await new Promise((res) => { const f = (n) => {
    t.push(n - last); last = n;
    if (info) { draws.push(info.render.drawCalls); tris.push(info.render.triangles); info.reset(); }
    if (n < end) requestAnimationFrame(f); else res(); }; requestAnimationFrame(f); });
  if (info) info.autoReset = auto;
  const q = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
  return { n: t.length, p50: +q(t, 0.5).toFixed(1), p95: +q(t, 0.95).toFixed(1), p99: +q(t, 0.99).toFixed(1), max: +q(t, 1).toFixed(1), over20: +((t.filter((x) => x > 20).length / t.length) * 100).toFixed(1), scale: nz?.gov?.scale?.toFixed(2), draws: draws.length > 1 ? q(draws.slice(1), 0.5) : undefined, drawsMax: draws.length > 1 ? q(draws.slice(1), 1) : undefined, tris: tris.length > 1 ? q(tris.slice(1), 0.5) : undefined };
}, sec);

const results = [];
const base = cfg.url || 'http://127.0.0.1:5200/';
let first = true;
for (const v of cfg.views || [{ q: '', name: 'shot.png' }]) {
  const url = base + (v.q ? '?' + v.q : '');
  const t0 = Date.now();
  if (first || v.reload !== false) await page.goto(url, { waitUntil: 'load' });
  first = false;
  await page.waitForFunction(() => window.__nz?.ready || document.querySelector('pre, #loader .err'), null, { timeout: 120000 });
  const ready = Date.now() - t0;
  if (v.eval) await page.evaluate(v.eval);
  for (const k of v.keys || []) {
    if (k.down) await page.keyboard.down(k.down);
    if (k.up) await page.keyboard.up(k.up);
    if (k.press) await page.keyboard.press(k.press);
    if (k.wait) await page.waitForTimeout(k.wait * 1000);
  }
  await page.waitForTimeout((v.wait ?? 4) * 1000);
  const r = v.measure ? await measure(v.measure) : {};
  if (v.name) await page.screenshot({ path: join(out, v.name) });
  const ret = v.ret ? await page.evaluate(v.ret) : undefined;
  results.push({ view: v.name, readyMs: ready, ...r, ret });
}
console.log(JSON.stringify({ results, logs: [...new Set(logs)].slice(-25) }, null, 1));
clearTimeout(hardStop);
await browser.close();
