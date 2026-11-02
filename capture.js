// Capture a TVO Learn page into a static, scriptless copy.
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

export const ALLOWED_HOSTS = (process.env.ALLOWED_HOSTS || 'tvolearn.com')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

// Extra hosts whose content may be pulled in when it is embedded in a TVO Learn
// page (an iframe). Empty by default: add only hosts you have been told are OK.
export const EMBED_HOSTS = (process.env.EMBED_HOSTS || '')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

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

export async function capture(inputUrl, outRoot, log = () => { }) {
    const url = validateUrl(inputUrl);
    const id = Date.now().toString(36) + '-' + sha1(url.href).slice(0, 6);
    const dir = path.join(outRoot, id);
    const assetsDir = path.join(dir, 'assets');
    await fs.mkdir(assetsDir, { recursive: true });

    const warnings = [];
    const resources = new Map(); // absolute url -> { file, type }
    const pending = [];
    let total = 0;

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
                    warnings.push('Did not load embedded content from ' + host + (isMain ? '' : ' (add it to EMBED_HOSTS if it is OK to copy)'));
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
                    if (body.length > MAX_FILE) { warnings.push('Skipped a file over 15 MB: ' + u); return; }
                    if (total + body.length > MAX_TOTAL) { warnings.push('Size limit reached, skipped: ' + u); return; }
                    total += body.length;
                    const ct = (res.headers()['content-type'] || '').split(';')[0].trim().toLowerCase();
                    const file = sha1(u).slice(0, 12) + extFor(ct, u);
                    await fs.writeFile(path.join(assetsDir, file), body);
                    resources.set(u, { file, type: rt });
                } catch { /* a response that cannot be read is simply not captured */ }
            })());
        });

        log('Opening ' + url.href);
        await page.goto(url.href, { waitUntil: 'networkidle', timeout: 60000 }).catch((e) => {
            warnings.push('Page did not fully settle: ' + e.message.split('\n')[0]);
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

        log('Taking a reference screenshot');
        await page.screenshot({ path: path.join(dir, 'screenshot.png'), fullPage: true }).catch((e) => {
            warnings.push('Screenshot failed: ' + e.message.split('\n')[0]);
        });

        await Promise.allSettled(pending);

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

        // Page: freeze the rendered DOM.
        log('Freezing the page');
        const mapFor = (prefix) => {
            const m = {};
            for (const [u, r] of resources) m[u] = prefix + 'assets/' + r.file;
            return m;
        };

        // Embedded frames (an iframe whose page lives on an allowed host) are
        // frozen on their own and linked from the copy. If a frame turns out to be
        // empty once frozen (for example it draws on a canvas), a picture of it is
        // saved instead.
        await page.$$eval('iframe', (els) => els.forEach((e, i) => e.setAttribute('data-embed', String(i))));
        const embeds = {};
        const frameElements = [];
        const frameStats = { placeholders: [], images: 0, imagesMissing: 0, cssAssetsMissing: 0 };
        await fs.mkdir(path.join(dir, 'frames'), { recursive: true });
        const handles = await page.$$('iframe');
        for (let i = 0; i < handles.length; i++) {
            try {
                const frame = await handles[i].contentFrame();
                if (!frame) continue;
                let host = '';
                try { host = new URL(frame.url()).hostname; } catch { /* ignore */ }
                if (!host || !frameHostAllowed(host)) continue;
                log('Capturing embedded content from ' + host);
                let shot = null;
                try { shot = await handles[i].screenshot(); } catch { /* ignore */ }
                const out = await frame.evaluate(freezeInPage, { map: mapFor('../'), embeds: {}, cidPrefix: 'f' + i + '-', TRANSPARENT_GIF });
                const textLen = out.elements.reduce((n, e) => n + (e.text ? e.text.length : 0), 0);
                if (out.elements.length < 4 || textLen < 20) {
                    if (!shot) continue;
                    const file = 'embed-' + i + '.png';
                    await fs.writeFile(path.join(assetsDir, file), shot);
                    embeds[i] = { kind: 'image', file: 'assets/' + file };
                    warnings.push('The embedded content from ' + host + ' had nothing to copy, so a picture of it was saved instead.');
                } else {
                    await fs.writeFile(path.join(dir, 'frames', 'f' + i + '.html'), out.html);
                    embeds[i] = { kind: 'frame', file: 'frames/f' + i + '.html' };
                    out.elements.forEach((e) => frameElements.push({ ...e, frame: 'f' + i }));
                    frameStats.placeholders.push(...out.stats.placeholders);
                    frameStats.images += out.stats.images;
                    frameStats.imagesMissing += out.stats.imagesMissing;
                    frameStats.cssAssetsMissing += out.stats.cssAssetsMissing;
                }
            } catch (e) {
                warnings.push('Could not capture an embedded frame: ' + e.message.split('\n')[0]);
            }
        }

        const frozen = await page.evaluate(freezeInPage, { map: mapFor(''), embeds, cidPrefix: '', TRANSPARENT_GIF });
        frozen.stats.placeholders.push(...frameStats.placeholders);
        frozen.stats.images += frameStats.images;
        frozen.stats.imagesMissing += frameStats.imagesMissing;
        frozen.stats.cssAssetsMissing += frameStats.cssAssetsMissing;
        frozen.elements.push(...frameElements);

        frozen.stats.cssAssetsMissing += cssMissing;

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
        removed: { scripts: 0, preloads: 0, cookieBanners: 0 },
        placeholders: []
    };
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
        docHeight: Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)
    };
}