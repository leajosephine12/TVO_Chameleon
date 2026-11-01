import express from 'express';
import path from 'node:path';
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { capture, validateUrl, ALLOWED_HOSTS } from './capture.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 3000);
const ROOT = path.resolve(process.env.DATA_DIR || path.join(__dirname, 'snapshots'));
await fs.mkdir(ROOT, { recursive: true });

const app = express();
app.disable('x-powered-by');

// Optional password protection: set APP_PASSWORD and the browser will ask for it
// (any user name works).
if (process.env.APP_PASSWORD) {
    const want = Buffer.from(process.env.APP_PASSWORD);
    app.use((req, res, next) => {
        const header = req.headers.authorization || '';
        const given = Buffer.from(Buffer.from(header.split(' ')[1] || '', 'base64').toString().split(':').slice(1).join(':'));
        if (given.length === want.length && crypto.timingSafeEqual(given, want)) return next();
        res.set('WWW-Authenticate', 'Basic realm="TVO capture"').status(401).send('Password required');
    });
}

app.use(express.json());

// Captured pages are served with a policy that blocks scripts and any request
// to another site, so a copy can only ever show what was saved.
app.use(
    '/snapshots',
    (req, res, next) => {
        res.set(
            'Content-Security-Policy',
            "sandbox allow-same-origin; default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; frame-src 'self'"
        );
        next();
    },
    express.static(ROOT)
);

// One capture at a time, to stay polite to the site.
const jobs = new Map();
let busy = false;

app.post('/api/capture', (req, res) => {
    let url;
    try {
        url = validateUrl(req.body && req.body.url);
    } catch (e) {
        return res.status(400).json({ error: e.message });
    }
    if (busy) return res.status(429).json({ error: 'A capture is already running. Try again in a moment.' });
    busy = true;
    const jobId = crypto.randomUUID();
    const job = { id: jobId, status: 'running', log: [], snapshot: null, error: null };
    jobs.set(jobId, job);
    capture(url.href, ROOT, (m) => job.log.push(m))
        .then((meta) => { job.status = 'done'; job.snapshot = meta; })
        .catch((e) => { job.status = 'error'; job.error = e.message; })
        .finally(() => { busy = false; });
    res.json({ jobId });
});

app.get('/api/jobs/:id', (req, res) => {
    const job = jobs.get(req.params.id);
    if (!job) return res.status(404).json({ error: 'Unknown job' });
    res.json(job);
});

app.get('/api/snapshots', async (req, res) => {
    const out = [];
    for (const d of await fs.readdir(ROOT, { withFileTypes: true })) {
        if (!d.isDirectory()) continue;
        try {
            out.push(JSON.parse(await fs.readFile(path.join(ROOT, d.name, 'meta.json'), 'utf8')));
        } catch { /* not a finished capture */ }
    }
    out.sort((a, b) => b.capturedAt.localeCompare(a.capturedAt));
    res.json(out);
});

app.get('/api/config', (req, res) => res.json({ allowedHosts: ALLOWED_HOSTS }));

app.use(express.static(path.join(__dirname, 'public')));

app.listen(PORT, () => {
    console.log('TVO capture running at http://localhost:' + PORT);
    console.log('Allowed hosts: ' + ALLOWED_HOSTS.join(', '));
    if (!process.env.APP_PASSWORD) console.log('No APP_PASSWORD set: anyone who can reach this port can use it.');
});