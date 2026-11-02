/**
 * Species resolution contract.
 *
 * The domain rule this exists to enforce: fuzzy matching may resolve *user
 * input* to a taxon, but nothing downstream may query data by anything except
 * the canonical id. `TaxonId` is branded so a raw string cannot be passed to a
 * data call by accident — the only way to obtain one is through the resolver
 * or `asTaxonId`, which validates against the loaded table.
 */

declare const TaxonIdBrand: unique symbol;

/** eBird `speciesCode` — the canonical identity for a taxon. */
export type TaxonId = string & { readonly [TaxonIdBrand]: true };

/** One row of the eBird/Clements taxonomy, trimmed to what resolution needs. */
export interface Taxon {
  taxonId: TaxonId;
  commonName: string;
  scientificName: string;
  category: string;
  family?: string;
  order?: string;
  /** Whether EcoPath's own catalogue holds this taxon. */
  inCatalogue?: boolean;
}

export type MatchKind =
  /** Query equals a name alias after normalisation. */
  | 'exact'
  /** Query equals a species code or banding/alpha code. */
  | 'code'
  /** Query matched by similarity scoring. */
  | 'fuzzy';

export interface Candidate {
  taxon: Taxon;
  /** 0..1. 1.0 means an exact alias hit. */
  confidence: number;
  /** The alias string that produced the score — shown back to the user. */
  matchedAlias: string;
  matchKind: MatchKind;
}

/**
 * The result of resolving free text.
 *
 * `resolved` still carries `alternatives` so the UI can offer a correction
 * affordance ("not this one?") — auto-resolution is never silent, per the rule
 * that the resolved name must be displayed back to the user.
 */
export type Resolution =
  | {
      status: 'resolved';
      taxon: Taxon;
      confidence: number;
      matchedAlias: string;
      matchKind: MatchKind;
      alternatives: Candidate[];
    }
  | { status: 'ambiguous'; query: string; candidates: Candidate[] }
  | { status: 'not_found'; query: string; candidates: [] };

/** One entry of the generated alias table. */
export interface AliasEntry {
  alias: string;
  taxonId: TaxonId;
  kind: MatchKind;
}

export interface AliasTable {
  taxa: Taxon[];
  aliases: AliasEntry[];
}
