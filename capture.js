// Capture a TVO Learn page into a static, scriptless copy.
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

export const ALLOWED_HOSTS = (process.env.ALLOWED_HOSTS || 'tvolearn.com')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

// Hosts whose content may be pulled in when it is embedded in a TVO Learn page
// (an iframe). tvopublishing.com is where TVO's own course modules are served
// from. Add more with the EMBED_HOSTS environment variable (comma-separated).
export const DEFAULT_EMBED_HOSTS = ['tvopublishing.com'];
export const EMBED_HOSTS = [
    ...DEFAULT_EMBED_HOSTS,
    ...(process.env.EMBED_HOSTS || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean)
];

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1']);

export function hostAllowed(host) {
    const h = String(host).toLowerCase();
    return ALLOWED_HOSTS.some((a) => h === a || h.endsWith('.' + a));
}

export function frameHostAllowed(host) {
    const h = String(host).toLowerCase();
    return hostAllowed(h) || EMBED_HOSTS.some((a) => h === a || h.endsWith('.' + a));
}

export function validateUrl(input) {
    let u;
    try {
        u = new URL(String(input || '').trim());
    } catch {
        throw new Error('That is not a valid link.');
    }
    const local = LOCAL_HOSTS.has(u.hostname);
    if (u.protocol !== 'https:' && !(local && u.protocol === 'http:')) {
        throw new Error('Only https links are allowed.');
    }
    if (u.username || u.password) throw new Error('Links with a username or password are not allowed.');
    if (!hostAllowed(u.hostname)) {
        throw new Error('Only TVO Learn links are allowed (tvolearn.com).');
    }
    u.hash = '';
    return u;
}

const TRANSPARENT_GIF = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';
const MAX_FILE = 15 * 1024 * 1024;
const MAX_TOTAL = 250 * 1024 * 1024;

const sha1 = (s) => crypto.createHash('sha1').update(s).digest('hex');

const EXT_BY_TYPE = {
    'text/css': '.css',
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/avif': '.avif',
    'image/svg+xml': '.svg',
    'image/x-icon': '.ico',
    'image/vnd.microsoft.icon': '.ico',
    'font/woff2': '.woff2',
    'font/woff': '.woff',
    'font/ttf': '.ttf',
    'font/otf': '.otf',
    'application/font-woff': '.woff',
    'application/font-woff2': '.woff2',
    'application/x-font-ttf': '.ttf',
    'application/x-font-opentype': '.otf',
    'application/vnd.ms-fontobject': '.eot'
};

function extFor(contentType, url) {
    if (EXT_BY_TYPE[contentType]) return EXT_BY_TYPE[contentType];
    const m = /\.([a-z0-9]{2,5})(?:$|[?#])/i.exec(new URL(url).pathname + '?');
    return m ? '.' + m[1].toLowerCase() : '';
}


function kindFor(ct, u) {
    let p = '';
    try { p = new URL(u).pathname.toLowerCase(); } catch { /* ignore */ }
    if (ct.includes('css') || p.endsWith('.css')) return 'stylesheet';
    if (ct.includes('font') || /\.(woff2?|ttf|otf|eot)$/.test(p)) return 'font';
    return 'image';
}

// Only fetch assets over https from public hosts (or from the hosts we were
// told to copy), never from private networks.
function assetUrlOk(u) {
    let x;
    try { x = new URL(u); } catch { return false; }
    if (x.username || x.password) return false;
    const h = x.hostname.toLowerCase();
    if (frameHostAllowed(h)) return x.protocol === 'https:' || (x.protocol === 'http:' && LOCAL_HOSTS.has(h));
    if (x.protocol !== 'https:') return false;
    if (LOCAL_HOSTS.has(h) || h.endsWith('.local') || h.endsWith('.internal') || !h.includes('.')) return false;
    if (/^\d+\.\d+\.\d+\.\d+$/.test(h) || h.includes(':')) return false;
    return true;
}

// Every file a stylesheet points at (url() and @import), as absolute links.
function cssRefs(css, base) {
    const out = [];
    const add = (u) => {
        const t = String(u || '').trim();
        if (!t || t.startsWith('data:') || t.startsWith('#')) return;
        try { out.push(new URL(t, base).href.split('#')[0]); } catch { /* ignore */ }
    };
    css.replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/gi, (m, _q, u) => { add(u); return m; });
    css.replace(/@import\s+(['"])([^'"]+)\1/gi, (m, _q, u) => { add(u); return m; });
    return out;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Wait until an embedded frame has loaded and stopped changing, scrolling it
// so that lazy content appears.
async function settleFrame(frame) {
    await frame.waitForLoadState('load', { timeout: 20000 }).catch(() => { });
    await frame.evaluate(async () => {
        const root = document.scrollingElement || document.documentElement;
        for (let y = 0; y < Math.min(root.scrollHeight, 20000); y += 400) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 80)); }
        window.scrollTo(0, 0);
    }).catch(() => { });
    let last = '', still = 0;
    const t0 = Date.now();
    while (Date.now() - t0 < 10000 && still < 3) {
        const sig = await frame.evaluate(() =>
            document.querySelectorAll('*').length + ':' + (document.body ? document.body.innerText.length : 0) + ':' + document.documentElement.scrollHeight
        ).catch(() => 'gone');
        if (sig === last) still++; else { still = 0; last = sig; }
        await sleep(400);
    }
}


// Open every accordion in a page or embedded frame (a static copy cannot toggle
// them). Uses the page's own "Expand All" button when there is one, otherwise
// clicks each collapsed heading, and opens <details> elements. Returns how many
// it opened.
//
// `strict` is used for the main page, where menus and drawers also use
// aria-expanded: it clicks only buttons that control a real panel and are not
// inside navigation, a header or a dialog, and never follows links.
export async function expandAll(frame, { strict = false } = {}) {
    return frame.evaluate(async ({ strict }) => {
        const wait = (ms) => new Promise((r) => setTimeout(r, ms));
        let opened = 0;

        const isAccordionHeading = (el) => {
            if (!strict) return el.matches('button, [role="button"], summary, a');
            return el.matches('button, [role="button"], summary')
                && !el.hasAttribute('aria-haspopup')
                && !el.closest('nav, header, dialog, [role="navigation"], [role="menu"], [role="dialog"]')
                && !!document.getElementById(el.getAttribute('aria-controls') || '');
        };

        document.querySelectorAll('details:not([open])').forEach((d) => { d.open = true; opened++; });

        const all = [...document.querySelectorAll('button, a, [role="button"]')]
            .find((b) => /^\s*expand all\s*$/i.test(b.textContent || '') && !b.disabled && b.getAttribute('aria-disabled') !== 'true');
        if (all) {
            all.click(); opened++;
            await wait(600);
        }

        // A panel with a data-src is a lazy lesson preview: the page builds it on click
        // but destroys the previous one, so these are built directly further down.
        const isLazyPreview = (heading) => {
            const panel = document.getElementById(heading.getAttribute('aria-controls') || '');
            return !!panel && panel.hasAttribute('data-src');
        };

        // Click each collapsed heading so the page loads whatever it loads on opening.
        const heads = [...document.querySelectorAll('[aria-expanded="false"]')]
            .filter(isAccordionHeading)
            .filter((h) => !isLazyPreview(h));
        for (const h of heads.slice(0, 200)) {
            try { h.click(); opened++; } catch { /* ignore */ }
            await wait(80);
        }
        await wait(500);

        // AMP accordions (amp-accordion): a section is open when it has the
        // `expanded` attribute. If the click did not do it, set it directly.
        document.querySelectorAll('amp-accordion section:not([expanded])').forEach((sec) => {
            sec.setAttribute('expanded', '');
            const hd = sec.querySelector('[aria-expanded]');
            if (hd) hd.setAttribute('aria-expanded', 'true');
            opened++;
        });

        // Some accordions only keep one section open at a time, so earlier clicks
        // may have closed sections again. What they loaded is still in the page:
        // open every heading that is still closed.
        document.querySelectorAll('[aria-expanded="false"][aria-controls]').forEach((h) => {
            if (!isAccordionHeading(h)) return;
            const p = document.getElementById(h.getAttribute('aria-controls'));
            if (!p) return;
            h.setAttribute('aria-expanded', 'true');
            p.removeAttribute('hidden');
            opened++;
        });

        // Lesson previews: every panel with a data-src gets one iframe aimed at that lesson.
        // The page may ship the iframe already (empty, or pointing at the wrong place), so an
        // existing one is reused; otherwise one is built, copying the look of a sibling.
        const sample = document.querySelector('[role="region"][data-src] iframe');
        document.querySelectorAll('[role="region"][data-src]').forEach((panel) => {
            let frame = panel.querySelector('iframe');
            if (!frame) {
                frame = document.createElement('iframe');
                if (sample) {
                    [...sample.attributes].forEach((a) => frame.setAttribute(a.name, a.value));
                } else {
                    frame.setAttribute('title', 'Course Preview');
                    frame.setAttribute('width', '100%');
                    frame.setAttribute('height', '100%');
                    frame.setAttribute('frameborder', '0');
                    frame.setAttribute('style', 'position:absolute; top:0; left:0');
                    frame.className = 'preview_iframe';
                }
                frame.id = panel.id ? panel.id.replace(/_panel$/, '') + '_iframe' : '';
                panel.appendChild(frame);
            }
            // Drop any src so the capture can load the previews one at a time (see loadLazyFrame).
            frame.removeAttribute('src');
            frame.setAttribute('data-lazy-src', panel.getAttribute('data-src'));
            panel.removeAttribute('hidden');
            const heading = document.getElementById(panel.getAttribute('aria-labelledby') || '');
            if (heading) heading.setAttribute('aria-expanded', 'true');
            opened++;
        });
        return opened;
    }, { strict }).catch(() => 0);
}

/**
 * Finds the tabs on the page and tags them for the frozen copy (see
 * makeTabsSwitchWithoutScripts in freezePage.js).
 *
 * A tab is recognised by ARIA (role="tab" or aria-selected, plus aria-controls) or by the
 * lesson player's convention of a link "link_<panelId>" next to a panel "<panelId>" (written
 * in different letter case: "link_mindson" opens "mindsOn"). Links that really go somewhere
 * are never treated as tabs.
 *
 * @returns {{count: number, initialIndex: number}} how many tabs there are and which one is showing
 */
function tagTabs() {
  const STYLE_PROPERTIES = ['background-color', 'color', 'font-weight', 'border-bottom-color', 'opacity'];

  const isShown = (element) =>
    getComputedStyle(element).display !== 'none' && element.getClientRects().length > 0;

  /** Finds an element by id, ignoring letter case when there is no exact match. */
  const findById = (id) =>
    document.getElementById(id) ||
    [...document.querySelectorAll('[id]')].find((element) => element.id.toLowerCase() === id.toLowerCase());

  /** The CSS declarations in `from` that differ from `other`, as "property:value;" text. */
  const styleDifference = (from, other) => {
    const own = getComputedStyle(from);
    const theirs = getComputedStyle(other);
    return STYLE_PROPERTIES.filter((name) => own.getPropertyValue(name) !== theirs.getPropertyValue(name))
      .map((name) => `${name}:${own.getPropertyValue(name)};`)
      .join('');
  };

  const isPlaceholderLink = (element) =>
    element.tagName !== 'A' || ['', '#'].includes((element.getAttribute('href') || '').trim());

  // Step 1: pair every tab with the panel it shows.
  const tabs = [];
  const candidates = 'a[id^="link_"], [role="tab"][aria-controls], [aria-controls][aria-selected]';
  document.querySelectorAll(candidates).forEach((trigger) => {
    const panelId = trigger.getAttribute('aria-controls') || trigger.id.replace(/^link_/, '');
    const panel = findById(panelId);
    const isUsable = panel && panel !== trigger && !panel.contains(trigger) && isPlaceholderLink(trigger);
    if (isUsable && !tabs.some((tab) => tab.panel === panel)) tabs.push({ trigger, panel });
  });
  if (tabs.length < 2) return { count: 0, initialIndex: 0 };

  // Step 2: tag the tabs. Panels sharing a parent form one group.
  const groupParents = [...new Set(tabs.map((tab) => tab.panel.parentElement))];
  const initialIndex = Math.max(
    0,
    tabs.findIndex((tab) => isShown(tab.panel)),
  );
  const initialTab = tabs[initialIndex];
  const otherTab = tabs.find((tab) => tab !== initialTab);

  tabs.forEach(({ trigger, panel }, index) => {
    panel.setAttribute('data-tab-panel', String(groupParents.indexOf(panel.parentElement)));
    trigger.setAttribute('data-tab-trigger', panel.id);
    trigger.setAttribute('data-tab-order', String(index));
  });
  initialTab.panel.setAttribute('data-tab-default', '');
  initialTab.trigger.setAttribute('data-tab-default-trigger', '');
  // How a selected tab looks compared with an unselected one, for the copy's CSS.
  initialTab.trigger.setAttribute(
    'data-tab-selected-style',
    styleDifference(initialTab.trigger, otherTab.trigger),
  );
  initialTab.trigger.setAttribute(
    'data-tab-unselected-style',
    styleDifference(otherTab.trigger, initialTab.trigger),
  );

  return { count: tabs.length, initialIndex };
}

/**
 * Clicks the tab tagged by tagTabs with this index. This is the fallback for a tab that
 * cannot take a real mouse click (see openTab in capture/tabs.js).
 *
 * @param {number} index  position of the tab in the order tagTabs found them
 */
function showTab(index) {
  const trigger = document.querySelector(`[data-tab-order="${index}"]`);
  if (trigger) trigger.click();
}

const TAB_CLICK_TIMEOUT_MS = 3000;
const TAB_REACTION_PAUSE_MS = 300; // the page's own click handler and any lazy loading

// Opens one tab. Some tab widgets only react to a real mouse press (not to a scripted
// click), so a real click comes first; a scripted click is the fallback.
async function openTab(frame, index) {
    try {
        await frame.locator(`[data-tab-order="${index}"]`).click({ timeout: TAB_CLICK_TIMEOUT_MS });
    } catch {
        await frame.evaluate(showTab, index).catch(() => { });
    }
    await sleep(TAB_REACTION_PAUSE_MS);
}

// Opens every tab of a tabbed layout, one at a time, so each tab's pictures, styles and
// collapsed sections are loaded before the page is frozen (the copy switches tabs with
// plain CSS, so every tab has to be in it). Returns the height of the tallest tab, or 0
// when there are no tabs. `strict` keeps the main page's menus closed (see expandAll).
async function visitEachTab(frame, { strict = false } = {}) {
    const { count, initialIndex } = await frame.evaluate(tagTabs).catch(() => ({ count: 0, initialIndex: 0 }));
    if (count === 0) return 0;

    let tallestTab = 0;
    for (let index = 0; index < count; index++) {
        await openTab(frame, index);
        await expandAll(frame, { strict });
        await settleFrame(frame);
        const height = await frame.evaluate(() => {
            let bottom = 0;
            for (const el of document.body.querySelectorAll('*')) {
                if (getComputedStyle(el).position === 'fixed') continue;
                const rect = el.getBoundingClientRect();
                if (rect.height > 0) bottom = Math.max(bottom, rect.bottom + window.scrollY);
            }
            return Math.ceil(bottom);
        }).catch(() => 0);
        tallestTab = Math.max(tallestTab, height);
    }
    await openTab(frame, initialIndex); // leave the page on the tab it started on
    return tallestTab;
}

// Starts loading a frame that was built without a src (a lazy lesson preview) and waits
// for it to leave about:blank. Loading these one at a time keeps a lesson server that
// copes badly with parallel requests happy; a failed load is retried twice.
async function loadLazyFrame(handle, source) {
    for (let attempt = 0; attempt < 3; attempt++) {
        await handle.evaluate((el, src) => { el.removeAttribute('data-lazy-src'); el.setAttribute('src', 'about:blank'); el.setAttribute('src', src); }, source);
        const frame = await handle.contentFrame();
        if (!frame) return null;
        for (let t = 0; t < 40 && (frame.url() === 'about:blank'); t++) await sleep(400);
        if (!frame.url().startsWith('chrome-error:') && frame.url() !== 'about:blank') return frame;
        await sleep(1500);
    }
    return null;
}

// Runs inside a page or frame: every file its inline styles, images and
// icons refer to.
function collectRefs() {
    const out = new Set();
    const add = (u) => { try { out.add(new URL(u, document.baseURI).href.split('#')[0]); } catch { /* ignore */ } };
    const scan = (css) => String(css || '').replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/gi, (m, _q, u) => {
        u = u.trim();
        if (u && !u.startsWith('data:') && !u.startsWith('#')) add(u);
        return m;
    });
    document.querySelectorAll('style').forEach((s) => scan(s.textContent));
    document.querySelectorAll('[style]').forEach((e) => scan(e.getAttribute('style')));
    [...document.styleSheets].forEach((sh) => {
        if (sh.href) return;
        try { [...sh.cssRules].forEach((r) => scan(r.cssText)); } catch { /* ignore */ }
    });
    document.querySelectorAll('img').forEach((i) => { const s = i.currentSrc || i.src; if (s && !s.startsWith('data:')) add(s); });
    document.querySelectorAll('link[rel~="stylesheet"], link[rel~="icon"]').forEach((l) => { if (l.href) add(l.href); });
    return [...out];
}

export async function capture(inputUrl, outRoot, log = () => { }) {
    const url = validateUrl(inputUrl);
    const id = Date.now().toString(36) + '-' + sha1(url.href).slice(0, 6);
    const dir = path.join(outRoot, id);
    const assetsDir = path.join(dir, 'assets');
    await fs.mkdir(assetsDir, { recursive: true });

    const warnings = [];
    const warn = (m) => { if (!warnings.includes(m)) warnings.push(m); };
    const resources = new Map(); // absolute url -> { file, type }
    const pending = [];
    const embedInfo = [];
    let total = 0;

    const store = async (u, body, ct, rt) => {
        if (resources.has(u)) return;
        if (body.length > MAX_FILE) { warn('Skipped a file over 15 MB: ' + u); return; }
        if (total + body.length > MAX_TOTAL) { warn('Size limit reached, skipped: ' + u); return; }
        total += body.length;
        const file = sha1(u).slice(0, 12) + extFor(ct, u);
        await fs.writeFile(path.join(assetsDir, file), body);
        resources.set(u, { file, type: rt });
    };

    log('Starting a headless browser');
    const browser = await chromium.launch({
        executablePath: process.env.CHROMIUM_PATH || undefined,
        args: ['--no-sandbox']
    });

    try {
        const context = await browser.newContext({
            viewport: { width: 1660, height: 900 },
            deviceScaleFactor: 1,
            serviceWorkers: 'block'
        });
        const page = await context.newPage();

        // Never leave the allowed hosts for a page or frame navigation, and skip
        // streaming media.
        await page.route('**/*', (route) => {
            const req = route.request();
            if (req.resourceType() === 'media') return route.abort();
            if (req.isNavigationRequest()) {
                let host = '';
                try { host = new URL(req.url()).hostname; } catch { /* ignore */ }
                const isMain = !req.frame().parentFrame();
                const ok = isMain ? hostAllowed(host) : frameHostAllowed(host);
                if (!ok && !req.url().startsWith('about:') && !req.url().startsWith('data:')) {
                    if (!isMain) warn('Not copied: embedded content from ' + host + ' (add it to EMBED_HOSTS if it is OK to copy)');
                    return route.abort();
                }
            }
            return route.continue();
        });

        // Save every image, stylesheet and font as it arrives.
        page.on('response', (res) => {
            pending.push((async () => {
                try {
                    const rt = res.request().resourceType();
                    if (!['stylesheet', 'image', 'font'].includes(rt)) return;
                    if (!res.ok()) return;
                    const u = res.url().split('#')[0];
                    if (u.startsWith('data:')) return;
                    const body = await res.body();
                    const ct = (res.headers()['content-type'] || '').split(';')[0].trim().toLowerCase();
                    await store(u, body, ct, rt);
                } catch { /* a response that cannot be read is simply not captured */ }
            })());
        });

        log('Opening ' + url.href);
        await page.goto(url.href, { waitUntil: 'networkidle', timeout: 60000 }).catch((e) => {
            warn('Page did not fully settle: ' + e.message.split('\n')[0]);
        });

        const finalUrl = new URL(page.url());
        if (!hostAllowed(finalUrl.hostname)) {
            throw new Error('The link redirected away from TVO Learn, so nothing was captured.');
        }

        log('Scrolling to load lazy images');
        await page.evaluate(async () => {
            await new Promise((resolve) => {
                let y = 0;
                const t = setInterval(() => {
                    window.scrollBy(0, 500);
                    y += 500;
                    if (y >= document.documentElement.scrollHeight + 500 || y > 40000) { clearInterval(t); resolve(); }
                }, 120);
            });
            window.scrollTo(0, 0);
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => { });
        await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => { });
        await page.waitForTimeout(600);

        // ---- The page's own accordions (course units and lesson previews) ------
        // They load their content when opened, so open them before anything is saved.
        const pageUrlBefore = page.url();
        const pageOpened = await expandAll(page.mainFrame(), { strict: true });
        if (pageOpened) {
            log('Opened ' + pageOpened + ' collapsed section(s) on the page');
            await settleFrame(page.mainFrame());
        }
        // Tab widgets: every tab must be in the copy, not only the one showing.
        await visitEachTab(page.mainFrame(), { strict: true });
        if (page.url() !== pageUrlBefore) warn('The page navigated while opening its sections; the copy may be incomplete.');

        // ---- Embedded frames: load them fully before anything is saved -------
        await page.$$eval('iframe', (els) => els.forEach((e, i) => e.setAttribute('data-embed', String(i))));
        const handles = await page.$$('iframe');
        const frameJobs = [];
        for (let i = 0; i < handles.length; i++) {
            try {
                const box = await handles[i].boundingBox().catch(() => null);
                if (!box || box.width < 24 || box.height < 24) continue; // tracking pixels, hidden helpers
                const lazySource = await handles[i].getAttribute('data-lazy-src').catch(() => null);
                const src = lazySource || (await handles[i].getAttribute('src').catch(() => null)) || (await handles[i].getAttribute('data-src').catch(() => null)) || '';
                await handles[i].scrollIntoViewIfNeeded().catch(() => { });
                let frame = lazySource ? await loadLazyFrame(handles[i], lazySource) : await handles[i].contentFrame();
                if (!frame) { warn('An embedded frame did not load' + (src ? ': ' + src : '') + '.'); continue; }
                // A lazy frame starts on about:blank; give it time to navigate.
                for (let t = 0; src && frame.url() === 'about:blank' && t < 20; t++) await sleep(400);
                let host = '';
                try { host = new URL(frame.url()).hostname; } catch { /* ignore */ }
                if (!host || !frameHostAllowed(host)) {
                    // A blocked host was already reported when its navigation was refused.
                    if (!host || host === 'chromewebdata') warn('An embedded frame did not load' + (src ? ': ' + src : '') + '.');
                    continue;
                }
                log('Waiting for embedded content from ' + host);
                await settleFrame(frame);
                const opened = await expandAll(frame);
                if (opened) {
                    log('Opened ' + opened + ' collapsed section(s) in the embedded content');
                    await settleFrame(frame);
                }
                // Visit every tab so its pictures load; the box must fit the tallest one.
                const tallestTab = await visitEachTab(frame);
                // Fit the iframe to what it holds, growing or shrinking it (the page may have
                // left it taller than its content), unless it fills a panel of fixed size
                // (the lesson previews): those scroll inside.
                const fillsPanel = await handles[i].evaluate((el) => getComputedStyle(el).position === 'absolute').catch(() => false);
                const measured = await frame.evaluate(() => {
                    // The document's scrollHeight never drops below the iframe's own height, so
                    // measure where the content actually ends: the lowest edge of any element
                    // that takes part in the layout (fixed overlays and empty boxes are ignored).
                    let bottom = 0;
                    for (const el of document.body.querySelectorAll('*')) {
                        if (getComputedStyle(el).position === 'fixed') continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.height > 0) bottom = Math.max(bottom, rect.bottom + window.scrollY);
                    }
                    return Math.ceil(bottom);
                }).catch(() => 0);
                const need = Math.max(measured, tallestTab);
                const have = (await handles[i].boundingBox().catch(() => null) || { height: 0 }).height;
                if (!fillsPanel && need >= 100 && Math.abs(need - have) > 4 && need < 20000) {
                    await handles[i].evaluate((el, h) => { el.style.height = h + 'px'; el.setAttribute('height', String(h)); }, need).catch(() => { });
                }
                frameJobs.push({ i, handle: handles[i], frame, host });
            } catch (e) {
                warn('Could not load an embedded frame: ' + e.message.split('\n')[0]);
            }
        }
        await page.evaluate(() => window.scrollTo(0, 0)).catch(() => { });
        await Promise.allSettled(pending);

        log('Taking a reference screenshot');
        await page.screenshot({ path: path.join(dir, 'screenshot.png'), fullPage: true }).catch((e) => {
            warn('Screenshot failed: ' + e.message.split('\n')[0]);
        });

        // ---- Files that were referenced but never requested -------------------
        // (hover backgrounds, fallback fonts, images in rules that did not apply,
        // anything the browser kept in memory). Fetch them directly.
        const tried = new Set();
        let fetchedExtra = 0;
        for (let round = 0; round < 3 && tried.size < 600; round++) {
            const want = new Set();
            for (const f of page.frames()) {
                try { (await f.evaluate(collectRefs)).forEach((u) => want.add(u)); } catch { /* frame gone or blocked */ }
            }
            for (const [cssUrl, r] of resources) {
                if (r.type !== 'stylesheet') continue;
                try { cssRefs(await fs.readFile(path.join(assetsDir, r.file), 'utf8'), cssUrl).forEach((u) => want.add(u)); } catch { /* ignore */ }
            }
            const todo = [...want].filter((u) => !resources.has(u) && !tried.has(u) && assetUrlOk(u));
            if (!todo.length) break;
            todo.forEach((u) => tried.add(u));
            log('Fetching ' + todo.length + ' referenced files that the page did not load');
            for (let k = 0; k < todo.length; k += 8) {
                await Promise.all(todo.slice(k, k + 8).map(async (u) => {
                    try {
                        const res = await context.request.get(u, { timeout: 15000, maxRedirects: 3, headers: { referer: url.href } });
                        if (!res.ok()) return;
                        const body = await res.body();
                        const ct = (res.headers()['content-type'] || '').split(';')[0].trim().toLowerCase();
                        const before = resources.size;
                        await store(u, body, ct, kindFor(ct, u));
                        if (resources.size > before) fetchedExtra++;
                    } catch { /* leave it blank */ }
                }));
            }
        }
        if (fetchedExtra) log('Saved ' + fetchedExtra + ' extra files');

        // Stylesheets: rewrite url() and @import so they point at the saved files.
        log('Saving ' + resources.size + ' assets');
        let cssMissing = 0;
        for (const [cssUrl, r] of resources) {
            if (r.type !== 'stylesheet') continue;
            const file = path.join(assetsDir, r.file);
            let css = await fs.readFile(file, 'utf8');
            css = css
                .replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/gi, (m, _q, u) => {
                    const t = u.trim();
                    if (t.startsWith('data:') || t.startsWith('#')) return m;
                    let hit = null;
                    try { hit = resources.get(new URL(t, cssUrl).href.split('#')[0]); } catch { /* ignore */ }
                    if (hit) return 'url("' + hit.file + '")';
                    cssMissing++;
                    return 'url("' + TRANSPARENT_GIF + '")';
                })
                .replace(/@import\s+(['"])([^'"]+)\1/gi, (m, _q, u) => {
                    let hit = null;
                    try { hit = resources.get(new URL(u, cssUrl).href.split('#')[0]); } catch { /* ignore */ }
                    return hit ? '@import "' + hit.file + '"' : '';
                });
            await fs.writeFile(file, css);
        }

        // ---- Freeze the frames, then the page ---------------------------------
        log('Freezing the page');
        const mapFor = (prefix) => {
            const m = {};
            for (const [u, r] of resources) m[u] = prefix + 'assets/' + r.file;
            return m;
        };
        const embeds = {};
        const frameElements = [];
        const frameStats = { placeholders: [], images: 0, imagesMissing: 0, cssAssetsMissing: 0, shadowRoots: 0 };
        await fs.mkdir(path.join(dir, 'frames'), { recursive: true });
        for (const { i, handle, frame, host } of frameJobs) {
            try {
                log('Copying embedded content from ' + host);
                let shot = null;
                try { shot = await handle.screenshot(); } catch { /* ignore */ }
                let out = await frame.evaluate(freezeInPage, { map: mapFor('../'), embeds: {}, cidPrefix: 'f' + i + '-', TRANSPARENT_GIF });
                const textLen = out.elements.reduce((n, e) => n + (e.text ? e.text.length : 0), 0);
                if ((out.elements.length < 4 || textLen < 20) && !out.stats.shadowRoots) {
                    if (!shot) { embedInfo.push({ index: i, host, result: 'empty' }); continue; }
                    const file = 'embed-' + i + '.png';
                    await fs.writeFile(path.join(assetsDir, file), shot);
                    embeds[i] = { kind: 'image', file: 'assets/' + file };
                    embedInfo.push({ index: i, host, result: 'picture' });
                    warn('The embedded content from ' + host + ' had nothing to copy (it probably draws itself with a script), so a picture of it was saved instead.');
                } else {
                    await fs.writeFile(path.join(dir, 'frames', 'f' + i + '.html'), out.html);
                    embeds[i] = { kind: 'frame', file: 'frames/f' + i + '.html' };
                    embedInfo.push({ index: i, host, result: 'copied', elements: out.elements.length });
                    out.elements.forEach((e) => frameElements.push({ ...e, frame: 'f' + i }));
                    frameStats.placeholders.push(...out.stats.placeholders);
                    frameStats.images += out.stats.images;
                    frameStats.imagesMissing += out.stats.imagesMissing;
                    frameStats.cssAssetsMissing += out.stats.cssAssetsMissing;
                    frameStats.shadowRoots += out.stats.shadowRoots;
                }
            } catch (e) {
                warn('Could not copy an embedded frame from ' + host + ': ' + e.message.split('\n')[0]);
                try {
                    const shot = await handle.screenshot();
                    const file = 'embed-' + i + '.png';
                    await fs.writeFile(path.join(assetsDir, file), shot);
                    embeds[i] = { kind: 'image', file: 'assets/' + file };
                    embedInfo.push({ index: i, host, result: 'picture' });
                } catch { embedInfo.push({ index: i, host, result: 'failed' }); }
            }
        }

        const frozen = await page.evaluate(freezeInPage, { map: mapFor(''), embeds, cidPrefix: '', TRANSPARENT_GIF });
        frozen.stats.placeholders.push(...frameStats.placeholders);
        frozen.stats.images += frameStats.images;
        frozen.stats.imagesMissing += frameStats.imagesMissing;
        frozen.stats.cssAssetsMissing += frameStats.cssAssetsMissing;
        frozen.elements.push(...frameElements);

        frozen.stats.cssAssetsMissing += cssMissing;
        frozen.stats.shadowRoots += frameStats.shadowRoots;
        if (frozen.stats.shadowRoots) warn(frozen.stats.shadowRoots + ' element(s) keep their content in shadow DOM, which is not copied.');
        if (frozen.stats.removed.hiddenFrames) log('Left out ' + frozen.stats.removed.hiddenFrames + ' hidden helper frame(s) (tracking, consent, payment widgets)');

        await fs.writeFile(path.join(dir, 'index.html'), frozen.html);
        await fs.writeFile(path.join(dir, 'elements.json'), JSON.stringify(frozen.elements));

        const meta = {
            id,
            sourceUrl: finalUrl.href,
            title: frozen.title,
            capturedAt: new Date().toISOString(),
            viewport: { width: 1660 },
            docHeight: frozen.docHeight,
            assets: resources.size,
            embeds: embedInfo,
            extraFilesFetched: fetchedExtra,
            elements: frozen.elements.length,
            stats: frozen.stats,
            warnings
        };
        await fs.writeFile(path.join(dir, 'meta.json'), JSON.stringify(meta, null, 2));
        log('Done: ' + frozen.elements.length + ' elements, ' + resources.size + ' assets, ' + frozen.stats.placeholders.length + ' placeholders');
        return meta;
    } finally {
        await browser.close();
    }
}

// Runs inside the page (or an embedded frame) and returns a frozen copy of it.
function freezeInPage({ map, embeds, cidPrefix, TRANSPARENT_GIF }) {
    const stats = {
        images: 0, imagesMissing: 0, stylesheets: 0, stylesheetsMissing: 0, cssAssetsMissing: 0,
        removed: { scripts: 0, preloads: 0, cookieBanners: 0, hiddenFrames: 0 },
        shadowRoots: 0,
        placeholders: []
    };
    // Measure the page as it is now, before anything is changed. scrollHeight
    // also counts off-screen helpers (hidden widgets), which would leave a blank
    // area under the footer.
    const boxHeight = Math.ceil(Math.max(
        document.documentElement.getBoundingClientRect().height,
        document.body ? document.body.getBoundingClientRect().bottom + scrollY : 0
    ));
    const fullHeight = Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0);
    const docHeight = boxHeight >= 200 && boxHeight <= fullHeight ? boxHeight : fullHeight;
    const abs = (u) => { try { return new URL(u, document.baseURI).href.split('#')[0]; } catch { return null; } };
    const local = (u) => { const a = u && abs(u); return a && map[a] ? map[a] : null; };

    // 1. Give every element a stable id and record its box and key styles.
    const SKIP = new Set(['SCRIPT', 'STYLE', 'LINK', 'META', 'NOSCRIPT', 'BR', 'TITLE', 'HEAD']);
    const elements = [];
    let n = 0;
    document.querySelectorAll('*').forEach((el) => {
        if (SKIP.has(el.tagName)) return;
        const cid = cidPrefix + 'c' + (++n);
        el.setAttribute('data-cid', cid);
        if (el.shadowRoot) stats.shadowRoots++;
        if (!el.closest('body')) return;
        const r = el.getBoundingClientRect();
        if (r.width < 1 || r.height < 1 || elements.length >= 8000) return;
        const cs = getComputedStyle(el);
        const own = [...el.childNodes].filter((c) => c.nodeType === 3).map((c) => c.textContent).join(' ').replace(/\s+/g, ' ').trim();
        elements.push({
            cid, tag: el.tagName.toLowerCase(),
            id: el.id || undefined,
            cls: typeof el.className === 'string' && el.className ? el.className : undefined,
            x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY),
            w: Math.round(r.width), h: Math.round(r.height),
            text: own ? own.slice(0, 160) : undefined,
            fontSize: cs.fontSize, fontWeight: cs.fontWeight, lineHeight: cs.lineHeight,
            color: cs.color, background: cs.backgroundColor
        });
    });

    const rewriteCss = (css) => css.replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/gi, (m, _q, u) => {
        const t = u.trim();
        if (t.startsWith('data:') || t.startsWith('#')) return m;
        const l = local(t);
        if (l) return 'url("' + l + '")';
        stats.cssAssetsMissing++;
        return 'url("' + TRANSPARENT_GIF + '")';
    });

    const placeholder = (el, label) => {
        const r = el.getBoundingClientRect();
        const d = document.createElement('div');
        d.className = 'cap-placeholder';
        d.setAttribute('role', 'img');
        d.setAttribute('aria-label', label);
        d.setAttribute('data-cid', el.getAttribute('data-cid') || '');
        const w = r.width > 0 ? Math.round(r.width) : 300;
        const h = r.height > 0 ? Math.round(r.height) : 150;
        d.style.cssText = 'box-sizing:border-box;display:flex;align-items:center;justify-content:center;text-align:center;background:#E3E7ED;color:#4A5568;font:13px system-ui,sans-serif;border:1px dashed #9AA6B5;width:' + w + 'px;height:' + h + 'px;max-width:100%;';
        d.textContent = label;
        el.replaceWith(d);
        stats.placeholders.push(label);
    };

    // 2. Styles that exist only in memory (CSS-in-JS, constructed sheets).
    document.querySelectorAll('style').forEach((s) => {
        if (!s.textContent.trim() && s.sheet) {
            try { s.textContent = [...s.sheet.cssRules].map((r) => r.cssText).join('\n'); } catch { /* cross-origin */ }
        }
    });
    (document.adoptedStyleSheets || []).forEach((sheet) => {
        try {
            const s = document.createElement('style');
            s.textContent = [...sheet.cssRules].map((r) => r.cssText).join('\n');
            document.head.appendChild(s);
        } catch { /* ignore */ }
    });
    document.querySelectorAll('style').forEach((s) => { s.textContent = rewriteCss(s.textContent); });

    // 3. Linked stylesheets and icons point at the saved copies.
    document.querySelectorAll('link').forEach((l) => {
        const rel = (l.getAttribute('rel') || '').toLowerCase();
        if (rel.includes('stylesheet')) {
            const loc = local(l.href);
            if (loc) { l.setAttribute('href', loc); stats.stylesheets++; }
            else { l.remove(); stats.stylesheetsMissing++; }
        } else if (rel.includes('icon')) {
            const loc = local(l.href);
            if (loc) l.setAttribute('href', loc); else l.remove();
        } else {
            l.remove();
            stats.removed.preloads++;
        }
    });

    // 4. Scripts and anything that could run or phone home.
    document.querySelectorAll('script, noscript, base').forEach((e) => { if (e.tagName === 'SCRIPT') stats.removed.scripts++; e.remove(); });
    document.querySelectorAll('meta[http-equiv]').forEach((m) => m.remove());
    document.querySelectorAll('*').forEach((el) => {
        [...el.attributes].forEach((a) => {
            if (/^on/i.test(a.name) || ['integrity', 'crossorigin', 'nonce'].includes(a.name)) el.removeAttribute(a.name);
        });
    });

    // 5. Inline style attributes.
    document.querySelectorAll('[style]').forEach((el) => {
        el.setAttribute('style', rewriteCss(el.getAttribute('style')));
    });

    // 6. Images.
    document.querySelectorAll('picture source').forEach((s) => s.remove());
    document.querySelectorAll('img').forEach((img) => {
        const r = img.getBoundingClientRect();
        const src = img.currentSrc || img.src || '';
        stats.images++;
        if (src.startsWith('data:')) {
            img.setAttribute('src', src);
        } else {
            const loc = local(src);
            if (loc) {
                img.setAttribute('src', loc);
            } else if (src) {
                stats.imagesMissing++;
                const w = Math.max(1, Math.round(r.width)), h = Math.max(1, Math.round(r.height));
                img.setAttribute('src', 'data:image/svg+xml;utf8,' + encodeURIComponent(
                    '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '"><rect width="100%" height="100%" fill="#E3E7ED"/></svg>'));
                img.setAttribute('width', String(w));
                img.setAttribute('height', String(h));
                stats.placeholders.push('Image not captured: ' + (img.getAttribute('alt') || src.slice(0, 80)));
            }
        }
        ['srcset', 'sizes', 'loading', 'data-src', 'data-srcset'].forEach((a) => img.removeAttribute(a));
    });
    document.querySelectorAll('canvas').forEach((c) => {
        try {
            const img = document.createElement('img');
            img.setAttribute('src', c.toDataURL('image/png'));
            img.setAttribute('alt', '');
            img.setAttribute('data-cid', c.getAttribute('data-cid') || '');
            img.style.cssText = 'width:' + c.getBoundingClientRect().width + 'px;height:' + c.getBoundingClientRect().height + 'px;';
            c.replaceWith(img);
        } catch { placeholder(c, 'Canvas not captured'); }
    });

    // 7. Things that cannot be frozen become labelled placeholders.
    document.querySelectorAll('iframe').forEach((f) => {
        const e = embeds[f.getAttribute('data-embed')];
        if (!e) {
            // Tracking pixels, consent and payment helpers: invisible, so nothing to show.
            const fr = f.getBoundingClientRect();
            const fcs = getComputedStyle(f);
            if (fr.width < 24 || fr.height < 24 || fcs.display === 'none' || fcs.visibility === 'hidden') {
                f.remove();
                stats.removed.hiddenFrames++;
                return;
            }
        }
        let host = 'embedded content';
        try { host = new URL(f.src).hostname; } catch { /* ignore */ }
        f.removeAttribute('data-embed');
        if (e && e.kind === 'frame') {
            ['srcdoc', 'allow', 'loading', 'sandbox', 'allowfullscreen'].forEach((a) => f.removeAttribute(a));
            f.setAttribute('src', e.file);
        } else if (e && e.kind === 'image') {
            const r = f.getBoundingClientRect();
            const img = document.createElement('img');
            img.setAttribute('src', e.file);
            img.setAttribute('alt', 'Embedded content (picture of the original)');
            img.setAttribute('data-cid', f.getAttribute('data-cid') || '');
            img.style.cssText = 'display:block;border:0;width:' + Math.round(r.width) + 'px;height:' + Math.round(r.height) + 'px;';
            f.replaceWith(img);
            stats.placeholders.push('Embedded content saved as a picture (' + host + ')');
        } else {
            placeholder(f, 'Embedded content (' + host + ')');
        }
    });
    document.querySelectorAll('video, audio').forEach((m) => placeholder(m, m.tagName === 'VIDEO' ? 'Video' : 'Audio'));
    document.querySelectorAll('object, embed').forEach((m) => placeholder(m, 'Embedded object'));

    // 8. Links become inert, keeping the original address for later.
    document.querySelectorAll('a[href]').forEach((a) => {
        const h = abs(a.getAttribute('href'));
        if (h) a.setAttribute('data-orig-href', h);
        a.setAttribute('href', '#');
        a.removeAttribute('target');
    });
    document.querySelectorAll('form').forEach((f) => f.removeAttribute('action'));

    // 8b. Tabs found by tagTabs switch with plain CSS: each tab links to its panel (#id)
    //     and :target shows the linked panel, so the copy works with scripts blocked.
    (() => {
      const panels = [...document.querySelectorAll('[data-tab-panel]')];
      if (panels.length === 0) return;

      const rules = [
        '[data-tab-panel]{display:none !important}',
        '[data-tab-panel][data-tab-default]{display:block !important}',
        '[data-tab-panel]:target{display:block !important}',
      ];
      const selected = document.querySelector('[data-tab-default-trigger][data-tab-selected-style]');
      const selectedStyle = selected ? selected.getAttribute('data-tab-selected-style') : '';
      const unselectedStyle = selected ? selected.getAttribute('data-tab-unselected-style') : '';
      /** Makes the tab a link to its panel; tabs that are not links (a <li>, a <button>) get one inside. */
      const linkTabToPanel = (trigger, panelId) => {
        if (trigger.tagName === 'A') {
          trigger.setAttribute('href', `#${panelId}`);
          return;
        }
        const link = document.createElement('a');
        link.setAttribute('href', `#${panelId}`);
        link.style.cssText = 'display:block;color:inherit;font:inherit;text-decoration:none;';
        link.append(...trigger.childNodes);
        trigger.append(link);
      };

      const important = (declarations) => declarations.replace(/;/g, ' !important;');

      // The page's script showed and hid panels with inline styles; the CSS above takes over.
      panels.forEach((panel) => {
        panel.style.removeProperty('display');
        if (!panel.getAttribute('style')) panel.removeAttribute('style');
      });

      document.querySelectorAll('[data-tab-trigger]').forEach((trigger) => {
        const panelId = trigger.getAttribute('data-tab-trigger');
        linkTabToPanel(trigger, panelId);
        if (trigger.hasAttribute('data-tab-default-trigger')) return;

        // While this tab's panel is the target, the first tab stops looking selected and this one starts to.
        const whenTarget = `body:has(#${CSS.escape(panelId)}:target)`;
        rules.push(`${whenTarget} [data-tab-trigger="${panelId}"]{${important(selectedStyle)}}`);
        rules.push(`${whenTarget} [data-tab-default-trigger]{${important(unselectedStyle)}}`);
      });

      // The panel shown at first hides again once another panel of its group is the target.
      new Set(panels.map((panel) => panel.getAttribute('data-tab-panel'))).forEach((group) => {
        const panelsOfGroup = `[data-tab-panel="${group}"]`;
        rules.push(
          `body:has(${panelsOfGroup}:target) ${panelsOfGroup}[data-tab-default]:not(:target){display:none !important}`,
        );
      });

      const style = document.createElement('style');
      style.textContent = rules.join('\n');
      document.head.append(style);
    })();

    // 9. Cookie and consent banners are not part of the page content.
    document.querySelectorAll('body *').forEach((el) => {
        const label = (el.id || '') + ' ' + (typeof el.className === 'string' ? el.className : '');
        if (/cookie|consent|gdpr/i.test(label) && ['fixed', 'sticky'].includes(getComputedStyle(el).position)) {
            el.remove();
            stats.removed.cookieBanners++;
        }
    });

    if (!document.querySelector('meta[charset]')) {
        const m = document.createElement('meta');
        m.setAttribute('charset', 'utf-8');
        document.head.prepend(m);
    }
    document.documentElement.setAttribute('data-captured-from', location.href);

    return {
        html: '<!doctype html>\n' + document.documentElement.outerHTML,
        stats, elements,
        title: document.title,
        docHeight
    };
}