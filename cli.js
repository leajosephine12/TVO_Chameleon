// Usage: node cli.js https://tvolearn.com/...
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { capture } from './capture.js';

const url = process.argv[2];
if (!url) {
    console.error('Usage: node cli.js <TVO Learn link>');
    process.exit(1);
}
const root = path.resolve(process.env.DATA_DIR || path.join(path.dirname(fileURLToPath(import.meta.url)), 'snapshots'));
try {
    const meta = await capture(url, root, (m) => console.log('-', m));
    console.log('\nSaved to', path.join(root, meta.id));
    console.log('Open', path.join(root, meta.id, 'index.html'));
} catch (e) {
    console.error('Failed:', e.message);
    process.exit(1);
}
