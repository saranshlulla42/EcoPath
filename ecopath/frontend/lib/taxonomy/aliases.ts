/**
 * Builds the alias table from an eBird/Clements taxonomy export.
 *
 * Every string a user might plausibly type for a taxon becomes an alias
 * pointing at one canonical id (the eBird `speciesCode`). Resolution then never
 * has to reason about name formats — it only scores query text against aliases.
 */

import { compact, normalize } from './normalize';
import type { AliasEntry, AliasTable, MatchKind, Taxon, TaxonId } from './types';

/** One row of the eBird taxonomy JSON (`/ref/taxonomy/ebird?fmt=json`). */
export interface EbirdTaxonRow {
  speciesCode: string;
  comName: string;
  sciName: string;
  category?: string;
  familyComName?: string;
  order?: string;
  bandingCodes?: string[];
  comNameCodes?: string[];
  sciNameCodes?: string[];
  /** Present on subspecies/form rows: the species they report as. */
  reportAs?: string;
}

export interface BuildOptions {
  /**
   * Categories treated as canonical targets. eBird also ships `issf`
   * (subspecies), `hybrid`, `slash`, `spuh`, `form` and `domestic`; those are
   * folded into their parent via `reportAs` rather than becoming targets of
   * their own, so a query can never resolve to something that is not a species.
   */
  categories?: string[];
  /** Scientific names EcoPath's own catalogue holds, for the `inCatalogue` flag. */
  catalogueSciNames?: Iterable<string>;
}

const DEFAULT_CATEGORIES = ['species'];

/**
 * Name variants worth generating for a common name.
 *
 * eBird uses a slash for genuinely unresolvable field pairs ("Little
 * Egret/Western Reef-Heron"); each side is a name a user may type.
 */
function commonNameVariants(comName: string): string[] {
  const out = new Set<string>();
  const add = (s: string) => {
    const n = normalize(s);
    if (n) out.add(n);
  };
  add(comName);
  if (comName.includes('/')) for (const part of comName.split('/')) add(part);
  // "Bar-tailed Godwit" -> "bartailed godwit": hyphen dropped rather than
  // spaced, which is how people often type compound modifiers.
  if (comName.includes('-')) add(comName.replace(/-/g, ''));
  return [...out];
}

function scientificNameVariants(sciName: string): string[] {
  const out = new Set<string>();
  const n = normalize(sciName);
  if (n) out.add(n);
  const parts = n.split(' ');
  // "Limosa lapponica" -> "l lapponica", the abbreviated form used in prose.
  if (parts.length >= 2 && parts[0].length > 0) {
    out.add(`${parts[0][0]} ${parts.slice(1).join(' ')}`);
  }
  return [...out];
}

export function buildAliasTable(rows: EbirdTaxonRow[], options: BuildOptions = {}): AliasTable {
  const categories = new Set(options.categories ?? DEFAULT_CATEGORIES);
  const catalogue = new Set([...(options.catalogueSciNames ?? [])].map(s => normalize(s)));

  const taxa: Taxon[] = [];
  const byId = new Map<string, Taxon>();
  const seen = new Set<string>();
  const aliases: AliasEntry[] = [];

  const push = (alias: string, taxonId: TaxonId, kind: MatchKind) => {
    const key = `${alias} ${taxonId}`;
    if (!alias || seen.has(key)) return;
    seen.add(key);
    aliases.push({ alias, taxonId, kind });
  };

  for (const row of rows) {
    if (!categories.has(row.category ?? 'species')) continue;
    const taxonId = row.speciesCode as TaxonId;
    const taxon: Taxon = {
      taxonId,
      commonName: row.comName,
      scientificName: row.sciName,
      category: row.category ?? 'species',
      family: row.familyComName,
      order: row.order,
      inCatalogue: catalogue.size ? catalogue.has(normalize(row.sciName)) : undefined,
    };
    taxa.push(taxon);
    byId.set(taxonId, taxon);

    for (const v of commonNameVariants(row.comName)) push(v, taxonId, 'exact');
    for (const v of scientificNameVariants(row.sciName)) push(v, taxonId, 'exact');
    push(normalize(row.speciesCode), taxonId, 'code');
    for (const list of [row.bandingCodes, row.comNameCodes, row.sciNameCodes]) {
      for (const code of list ?? []) push(normalize(code), taxonId, 'code');
    }
  }

  // Subspecies and forms resolve to the species they report as, so typing a
  // subspecies name lands on a real taxon rather than nothing.
  for (const row of rows) {
    if (categories.has(row.category ?? 'species')) continue;
    const parent = row.reportAs ? byId.get(row.reportAs) : undefined;
    if (!parent) continue;
    for (const v of commonNameVariants(row.comName)) push(v, parent.taxonId, 'exact');
    push(normalize(row.speciesCode), parent.taxonId, 'code');
  }

  return { taxa, aliases };
}

/** Exact-match index: normalised alias (and its compacted form) to entries. */
export function buildExactIndex(table: AliasTable): Map<string, AliasEntry[]> {
  const index = new Map<string, AliasEntry[]>();
  for (const entry of table.aliases) {
    for (const key of new Set([entry.alias, compact(entry.alias)])) {
      const bucket = index.get(key);
      if (bucket) bucket.push(entry);
      else index.set(key, [entry]);
    }
  }
  return index;
}
