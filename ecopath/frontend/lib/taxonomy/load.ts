/**
 * Lazy, cached construction of the species resolver.
 *
 * The taxonomy is fetched once and the index built once (~460ms for ~17k taxa),
 * then every resolution is local and sub-millisecond. Nothing here touches the
 * network per query, so the command bar stays offline-capable after first load.
 */

import { buildAliasTable, type EbirdTaxonRow } from './aliases';
import { createResolver, type Resolver } from './resolver';

/** Where `scripts/build-taxonomy.mjs` writes its output. */
export const TAXONOMY_URL = '/taxonomy/ebird-taxonomy.json';

let pending: Promise<Resolver> | null = null;

export interface LoadOptions {
  url?: string;
  /**
   * Scientific names EcoPath's catalogue holds. Resolution succeeds regardless;
   * this only sets `inCatalogue`, so the UI can say "we know this bird but hold
   * no observations for it" rather than collapsing that into "not found".
   */
  catalogueSciNames?: string[];
  fetchImpl?: typeof fetch;
}

async function build(options: LoadOptions): Promise<Resolver> {
  const doFetch = options.fetchImpl ?? fetch;
  const resp = await doFetch(options.url ?? TAXONOMY_URL);
  if (!resp.ok) {
    throw new Error(
      `Taxonomy not available (${resp.status}). Run: node scripts/build-taxonomy.mjs <ebird_taxonomy.json>`,
    );
  }
  const rows = (await resp.json()) as EbirdTaxonRow[];
  return createResolver(
    buildAliasTable(rows, { catalogueSciNames: options.catalogueSciNames }),
  );
}

/**
 * The shared resolver. Concurrent callers await the same construction rather
 * than each building their own index.
 */
export function getResolver(options: LoadOptions = {}): Promise<Resolver> {
  if (!pending) {
    pending = build(options).catch(err => {
      // Let a later call retry rather than caching the failure forever.
      pending = null;
      throw err;
    });
  }
  return pending;
}

/** Drop the cached resolver — for tests, or after the taxonomy is replaced. */
export function resetResolver(): void {
  pending = null;
}
