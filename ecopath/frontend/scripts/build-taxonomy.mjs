#!/usr/bin/env node
/**
 * Prepares the eBird/Clements taxonomy for local species resolution.
 *
 * Reads the taxonomy export, keeps only the fields resolution needs, and writes
 * it where the app can fetch it. The alias table and search index are derived
 * from this at load time (~460ms once, then cached), so there is nothing to
 * regenerate when the resolver changes — only when the taxonomy does.
 *
 *   node scripts/build-taxonomy.mjs path/to/ebird_taxonomy.json
 *   node scripts/build-taxonomy.mjs --fetch          # needs EBIRD_API_KEY
 *
 * Deliberately plain JavaScript: it only reshapes JSON, so it needs no
 * TypeScript runner and stays runnable with bare node.
 */

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(HERE, '..', 'public', 'taxonomy');
const OUT_FILE = join(OUT_DIR, 'ebird-taxonomy.json');

const EBIRD_URL = 'https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json';

/** Only what resolution reads. Everything else is dropped to keep the payload small. */
const KEEP = [
  'speciesCode',
  'comName',
  'sciName',
  'category',
  'familyComName',
  'order',
  'bandingCodes',
  'comNameCodes',
  'sciNameCodes',
  'reportAs',
];

function trim(row) {
  const out = {};
  for (const key of KEEP) {
    const value = row[key];
    if (value === undefined || value === null) continue;
    if (Array.isArray(value) && value.length === 0) continue;
    out[key] = value;
  }
  return out;
}

async function loadRows(args) {
  if (args.includes('--fetch')) {
    const key = process.env.EBIRD_API_KEY;
    if (!key) throw new Error('EBIRD_API_KEY is not set; pass a file path instead of --fetch');
    process.stderr.write(`fetching ${EBIRD_URL}\n`);
    const resp = await fetch(EBIRD_URL, { headers: { 'X-eBirdApiToken': key } });
    if (!resp.ok) throw new Error(`eBird returned ${resp.status} ${resp.statusText}`);
    return resp.json();
  }

  const path = args.find(a => !a.startsWith('--'));
  if (!path) {
    throw new Error(
      'Usage: node scripts/build-taxonomy.mjs <ebird_taxonomy.json> | --fetch',
    );
  }
  const text = await readFile(resolve(path), 'utf8');
  const parsed = JSON.parse(text);
  if (!Array.isArray(parsed)) throw new Error('Expected a JSON array of taxonomy rows');
  return parsed;
}

async function main() {
  const rows = await loadRows(process.argv.slice(2));

  const missing = rows.filter(r => !r.speciesCode || !r.comName || !r.sciName);
  if (missing.length) {
    throw new Error(
      `${missing.length} row(s) lack speciesCode/comName/sciName — is this the eBird taxonomy export?`,
    );
  }

  const trimmed = rows.map(trim);
  const byCategory = trimmed.reduce((acc, r) => {
    const key = r.category ?? 'species';
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});

  await mkdir(OUT_DIR, { recursive: true });
  const json = JSON.stringify(trimmed);
  await writeFile(OUT_FILE, json);

  process.stdout.write(`wrote ${OUT_FILE}\n`);
  process.stdout.write(`  rows: ${trimmed.length}  (${(json.length / 1024 / 1024).toFixed(2)} MB)\n`);
  for (const [category, n] of Object.entries(byCategory).sort((a, b) => b[1] - a[1])) {
    process.stdout.write(`    ${category}: ${n}\n`);
  }
}

main().catch(err => {
  process.stderr.write(`${err.message}\n`);
  process.exit(1);
});
