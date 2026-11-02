import type { EbirdTaxonRow } from '../../lib/taxonomy/aliases';
import { TAXONOMY_FIXTURE } from './taxonomy.fixture';

/**
 * A synthetic taxonomy with realistic *token frequencies*.
 *
 * This matters more than it sounds. A naive generator that cycles 20 nouns over
 * 17k names makes every common word match ~850 taxa, which is nothing like the
 * real file and turns a retrieval benchmark into a measurement of the
 * generator. eBird's actual distribution is long-tailed with a few very heavy
 * group nouns, so that shape is reproduced here — including "Warbler", which is
 * genuinely the worst case at roughly 400 species.
 */

/** Group nouns and how many species carry each, mirroring the real long tail. */
const HEAVY_NOUNS: ReadonlyArray<readonly [string, number]> = [
  ['Warbler', 400],
  ['Tyrant', 200],
  ['Hummingbird', 180],
  ['Flycatcher', 160],
  ['Tanager', 150],
  ['Sparrow', 130],
  ['Antbird', 120],
  ['Pigeon', 110],
  ['Parrot', 100],
  ['Owl', 90],
  ['Finch', 85],
  ['Thrush', 80],
  ['Woodpecker', 75],
  ['Kingfisher', 70],
  ['Duck', 60],
  ['Eagle', 55],
  ['Tern', 45],
  ['Heron', 40],
  ['Godwit', 4],
];

const MODIFIERS = [
  'Greater', 'Lesser', 'Common', 'Northern', 'Southern', 'Eastern', 'Western',
  'Spotted', 'Striped', 'Banded', 'Crested', 'Collared', 'Rufous', 'Ashy',
  'Slender-billed', 'Broad-billed', 'Long-tailed', 'Short-tailed', 'White-browed',
  'Black-headed', 'Golden', 'Silver', 'Bronze', 'Emerald', 'Scarlet', 'Azure',
  'Olive', 'Chestnut', 'Cinnamon', 'Dusky', 'Pallid', 'Sooty', 'Streaked',
  'Barred', 'Scaled', 'Plain', 'Painted', 'Masked', 'Hooded', 'Crowned',
];

const ONSETS = ['tor', 'mir', 'cal', 'pha', 'zos', 'lan', 'dic', 'pyc', 'cis', 'emb',
  'fic', 'mot', 'egr', 'ard', 'fal', 'cor', 'pas', 'tur', 'phy', 'ste',
  'gly', 'nyc', 'orb', 'ven', 'kal', 'sib', 'rhe', 'ums', 'jac', 'wex'];
const CODAS = ['ella', 'ura', 'opsis', 'ites', 'anthus', 'ornis', 'ceps', 'ura2', 'idae', 'ulus',
  'astra', 'enia', 'oides', 'arius', 'icola', 'iformis', 'ipes', 'ostris', 'ythra', 'onota'];

/**
 * Genus names distributed the way real ones are: a few species each across
 * thousands of *distinct* genera.
 *
 * Both the count and the spelling matter. Cycling twenty roots puts ~850
 * species in every genus; numbering them ("Limosa0", "Limosa1") keeps them
 * distinct but leaves a shared prefix, so a prefix search on "limosa" still
 * sweeps all 850. Either way a binomial query looks far more expensive than it
 * is against the real file.
 */
function genusFor(i: number): string {
  const bucket = Math.floor(i / 5);
  const onset = ONSETS[bucket % ONSETS.length];
  const coda = CODAS[Math.floor(bucket / ONSETS.length) % CODAS.length];
  const cycle = Math.floor(bucket / (ONSETS.length * CODAS.length));
  const name = `${onset}${coda}${cycle || ''}`;
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** A long tail of one-off group nouns, so most names share little vocabulary. */
function tailNoun(i: number): string {
  const roots = ['grebe', 'shrike', 'babbler', 'weaver', 'pipit', 'lark', 'bunting',
    'crake', 'rail', 'snipe', 'plover', 'stint', 'curlew', 'ibis', 'stork'];
  return `${roots[i % roots.length]}${Math.floor(i / roots.length)}`;
}

export function syntheticTaxonomy(count: number): EbirdTaxonRow[] {
  const rows: EbirdTaxonRow[] = [...TAXONOMY_FIXTURE];
  const used = new Set(rows.map(r => r.comName.toLowerCase()));
  let i = 0;

  const push = (comName: string) => {
    if (used.has(comName.toLowerCase()) || rows.length >= count) return;
    used.add(comName.toLowerCase());
    rows.push({
      speciesCode: `syn${i.toString(36)}`,
      comName,
      sciName: `${genusFor(i)} synthetica${i}`,
      category: 'species',
      familyComName: 'Synthetic Family',
      order: 'Passeriformes',
    });
    i++;
  };

  // Heavy group nouns first, at their real-ish frequencies.
  for (const [noun, frequency] of HEAVY_NOUNS) {
    for (let k = 0; k < frequency && rows.length < count; k++) {
      const modifier = MODIFIERS[k % MODIFIERS.length];
      const suffix = k >= MODIFIERS.length ? ` ${Math.floor(k / MODIFIERS.length)}` : '';
      push(`${modifier}${suffix} ${noun}`);
    }
  }

  // Then the long tail, where each noun is nearly unique.
  let t = 0;
  while (rows.length < count) {
    push(`${MODIFIERS[t % MODIFIERS.length]} ${tailNoun(t)}`);
    t++;
  }

  return rows;
}
