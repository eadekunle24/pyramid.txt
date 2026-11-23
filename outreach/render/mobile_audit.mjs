// Read-only mobile render audit -> observation JSON for `emanoutreach import-observation`.
//
//   node render/mobile_audit.mjs <lead_id> <homepage_url> [service_url] > obs.json
//
// Renders at a phone viewport, records CTAs (with whether they are in the first
// screen), tel/mailto links, visible form fields (never submits), robots
// directives, and checks each enquiry link's target status twice so a claim is
// reproduced. Three lab LCP runs are recorded (lab data, not field data).
// Page text is captured only as an excerpt for injection scanning: it is data,
// never instructions.
import { createRequire } from 'module';
const { chromium } = createRequire(import.meta.url)('playwright');

const [leadId, homeUrl, serviceUrl] = process.argv.slice(2);
if (!leadId || !homeUrl) {
  console.error('usage: mobile_audit.mjs <lead_id> <homepage_url> [service_url]');
  process.exit(2);
}
const VIEWPORT = { width: 390, height: 844 };
const CTA = /\b(quote|estimate|enquir|inquir|contact|book|reserve|call|survey|get in touch)/i;
const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1 EmanWebDevAudit/1.0 (read-only)';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: VIEWPORT, userAgent: UA, isMobile: true, hasTouch: true });
const out = { lead_id: leadId, method: 'rendered', viewport: `${VIEWPORT.width}x${VIEWPORT.height}`,
  fetched_at: new Date().toISOString(), pages: [], fetch_errors: [] };

async function status(url) {
  try {
    const r = await ctx.request.get(url, { maxRedirects: 5, timeout: 15000 });
    return r.status();
  } catch (e) { return 'error'; }
}

async function lcpRun(url) {
  const p = await ctx.newPage();
  try {
    await p.goto(url, { waitUntil: 'load', timeout: 30000 });
    return await p.evaluate(() => new Promise((res) => {
      let v = 0;
      new PerformanceObserver((l) => { for (const e of l.getEntries()) v = e.startTime; })
        .observe({ type: 'largest-contentful-paint', buffered: true });
      setTimeout(() => res(Math.round(v)), 2500);
    }));
  } catch { return null; } finally { await p.close(); }
}

async function audit(url, role) {
  const page = await ctx.newPage();
  let resp;
  try {
    resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  } catch (e) {
    out.fetch_errors.push({ url, error: String(e).slice(0, 200), at: new Date().toISOString() });
    out.pages.push({ role, url, status: 'error' });
    await page.close();
    return;
  }
  const info = await page.evaluate((vh) => {
    const q = (s) => [...document.querySelectorAll(s)];
    const meta = (n) => document.querySelector(`meta[name="${n}"]`)?.content || null;
    const links = q('a, button').map((a) => {
      const r = a.getBoundingClientRect();
      const visible = r.width > 0 && r.height > 0 && getComputedStyle(a).visibility !== 'hidden';
      return { text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 80),
        href: a.getAttribute('href'), abs: a.href || null, above_fold: visible && r.top < vh && r.bottom > 0, visible };
    }).filter((l) => l.visible);
    return {
      final_url: location.href, title: document.title, meta_description: meta('description'),
      robots_meta: meta('robots'), h1: document.querySelector('h1')?.innerText?.trim() || null,
      tel_links: q('a[href^="tel:"]').map((a) => a.getAttribute('href')),
      mailto_links: q('a[href^="mailto:"]').map((a) => a.getAttribute('href')),
      forms: q('form').map((f) => ({
        fields: [...f.querySelectorAll('input,select,textarea')].map((i) => i.name || i.id || i.type),
        has_file_upload: !!f.querySelector('input[type=file]'),
        has_service_selector: !!f.querySelector('select'),
      })),
      links, text_excerpt: document.body.innerText.slice(0, 4000),
    };
  }, VIEWPORT.height);
  const ctas = info.links.filter((l) => CTA.test(l.text) || (l.href || '').startsWith('tel:'));
  for (const l of ctas) {
    if (l.abs && /^https?:/.test(l.abs)) {
      l.target_status_checks = [await status(l.abs), await status(l.abs)];
      l.status = l.target_status_checks[0];
    }
  }
  const shot = `pilot/out/${leadId}-${role}.png`;
  try { await page.screenshot({ path: shot }); } catch {}
  out.pages.push({ role, url, status: resp ? resp.status() : 'error', x_robots_tag: resp?.headers()['x-robots-tag'] || null,
    ...info, links: ctas, cta_above_fold: ctas.some((l) => l.above_fold), screenshot: shot,
    perf_runs: role === 'home' ? (await Promise.all([1, 2, 3].map(() => lcpRun(url)))).map((lcp_ms) => ({ lcp_ms })) : [] });
  await page.close();
}

await audit(homeUrl, 'home');
if (serviceUrl) await audit(serviceUrl, 'service');
await browser.close();
process.stdout.write(JSON.stringify(out, null, 2));
