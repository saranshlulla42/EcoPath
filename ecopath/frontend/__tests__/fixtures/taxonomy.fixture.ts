/**
 * A slice of the eBird taxonomy, shaped exactly like the real export.
 *
 * Chosen to contain the collisions that matter rather than to be representative:
 * four godwits that differ by one modifier, two "Arctic" birds, several terns,
 * and two species whose names merely *contain* "tern" ("Eastern", "Western") —
 * which is what the current substring resolver wrongly returns today.
 *
 * Codes and scientific names are the real eBird ones, so behaviour here matches
 * behaviour against the full file.
 */

import type { EbirdTaxonRow } from '../../lib/taxonomy/aliases';

export const TAXONOMY_FIXTURE: EbirdTaxonRow[] = [
  // ── the godwit family: the near-miss case ────────────────────────────────
  {
    speciesCode: 'bartgo',
    comName: 'Bar-tailed Godwit',
    sciName: 'Limosa lapponica',
    category: 'species',
    familyComName: 'Sandpipers and Allies',
    order: 'Charadriiformes',
    bandingCodes: ['BTGO'],
    comNameCodes: ['BTGO'],
    sciNameCodes: ['LILA'],
  },
  {
    speciesCode: 'bktgod',
    comName: 'Black-tailed Godwit',
    sciName: 'Limosa limosa',
    category: 'species',
    familyComName: 'Sandpipers and Allies',
    order: 'Charadriiformes',
    bandingCodes: [],
    comNameCodes: ['BTGO'], // deliberately shared with Bar-tailed: codes collide
    sciNameCodes: ['LILI'],
  },
  {
    speciesCode: 'hudgod',
    comName: 'Hudsonian Godwit',
    sciName: 'Limosa haemastica',
    category: 'species',
    familyComName: 'Sandpipers and Allies',
    order: 'Charadriiformes',
    comNameCodes: ['HUGO'],
  },
  {
    speciesCode: 'margod',
    comName: 'Marbled Godwit',
    sciName: 'Limosa fedoa',
    category: 'species',
    familyComName: 'Sandpipers and Allies',
    order: 'Charadriiformes',
    comNameCodes: ['MAGO'],
  },

  // ── two "Arctic" birds: the contraction case ─────────────────────────────
  {
    speciesCode: 'arcter',
    comName: 'Arctic Tern',
    sciName: 'Sterna paradisaea',
    category: 'species',
    familyComName: 'Gulls, Terns, and Skimmers',
    order: 'Charadriiformes',
    comNameCodes: ['ARTE'],
  },
  {
    speciesCode: 'arcwar1',
    comName: 'Arctic Warbler',
    sciName: 'Phylloscopus borealis',
    category: 'species',
    familyComName: 'Leaf Warblers',
    order: 'Passeriformes',
    comNameCodes: ['ARWA'],
  },

  // ── more terns, so "tern" is genuinely ambiguous ─────────────────────────
  {
    speciesCode: 'whiter2',
    comName: 'Whiskered Tern',
    sciName: 'Chlidonias hybrida',
    category: 'species',
    familyComName: 'Gulls, Terns, and Skimmers',
    order: 'Charadriiformes',
  },
  {
    speciesCode: 'caster1',
    comName: 'Caspian Tern',
    sciName: 'Hydroprogne caspia',
    category: 'species',
    familyComName: 'Gulls, Terns, and Skimmers',
    order: 'Charadriiformes',
  },

  // ── decoys: names containing "tern" that are not terns ───────────────────
  {
    speciesCode: 'rerswa1',
    comName: 'Eastern Red-rumped Swallow',
    sciName: 'Cecropis daurica',
    category: 'species',
    familyComName: 'Swallows',
    order: 'Passeriformes',
  },
  {
    speciesCode: 'eaywag',
    comName: 'Western Yellow Wagtail',
    sciName: 'Motacilla flava',
    category: 'species',
    familyComName: 'Wagtails and Pipits',
    order: 'Passeriformes',
  },

  // ── spelling variants and ordinary lookups ───────────────────────────────
  {
    speciesCode: 'greher1',
    comName: 'Gray Heron',
    sciName: 'Ardea cinerea',
    category: 'species',
    familyComName: 'Herons, Egrets, and Bitterns',
    order: 'Pelecaniformes',
    comNameCodes: ['GRHE'],
  },
  {
    speciesCode: 'houspa',
    comName: 'House Sparrow',
    sciName: 'Passer domesticus',
    category: 'species',
    familyComName: 'Old World Sparrows',
    order: 'Passeriformes',
    bandingCodes: ['HOSP'],
    comNameCodes: ['HOSP'],
  },
  {
    speciesCode: 'sarcra1',
    comName: 'Sarus Crane',
    sciName: 'Antigone antigone',
    category: 'species',
    familyComName: 'Cranes',
    order: 'Gruiformes',
  },
  {
    speciesCode: 'grebus1',
    comName: 'Great Indian Bustard',
    sciName: 'Ardeotis nigriceps',
    category: 'species',
    familyComName: 'Bustards',
    order: 'Otidiformes',
  },

  // ── a slash taxon: one string legitimately naming two birds ──────────────
  {
    speciesCode: 'litegr',
    comName: 'Little Egret',
    sciName: 'Egretta garzetta',
    category: 'species',
    familyComName: 'Herons, Egrets, and Bitterns',
    order: 'Pelecaniformes',
  },

  // ── a subspecies, which must fold into its parent, not become a target ───
  {
    speciesCode: 'houspa2',
    comName: 'House Sparrow (Indian)',
    sciName: 'Passer domesticus indicus',
    category: 'issf',
    reportAs: 'houspa',
  },
];

/** Scientific names EcoPath's own catalogue holds — Arctic Tern deliberately absent. */
export const CATALOGUE_SCI_NAMES = [
  'Limosa lapponica',
  'Limosa limosa',
  'Ardea cinerea',
  'Passer domesticus',
  'Antigone antigone',
  'Ardeotis nigriceps',
  'Egretta garzetta',
  'Chlidonias hybrida',
  'Hydroprogne caspia',
];
