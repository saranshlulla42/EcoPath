/**
 * Approximate visual centre ("pole of inaccessibility") for every Indian
 * admin-1 unit, as [longitude, latitude].
 *
 * These are not geometric centroids — they are the point furthest from any
 * border of the unit's largest polygon, computed from the same
 * public/geojson/india-states.geojson that the chat maps render. That matters
 * for concave states such as Gujarat and Kerala, where a true centroid can
 * land in the sea. Every point here is guaranteed to sit inside its own state,
 * so a label anchored to it never floats off the shape it names.
 */
export const STATE_CENTROIDS: Record<string, [number, number]> = {
  'AN': [92.86, 12.57],  // Andaman and Nicobar Islands
  'AP': [78.85, 14.81],  // Andhra Pradesh
  'AR': [94.63, 28.44],  // Arunachal Pradesh
  'AS': [93.0, 26.21],  // Assam
  'BR': [86.09, 25.67],  // Bihar
  'CH': [76.78, 30.75],  // Chandigarh
  'CT': [81.74, 21.57],  // Chhattisgarh
  'DH': [72.98, 20.2],  // Dadra and Nagar Haveli and Daman and Diu
  'DL': [77.1, 28.68],  // Delhi
  'GA': [74.07, 15.29],  // Goa
  'GJ': [71.8, 23.43],  // Gujarat
  'HP': [77.3, 31.9],  // Himachal Pradesh
  'HR': [76.25, 29.06],  // Haryana
  'JH': [84.98, 23.5],  // Jharkhand
  'JK': [75.02, 33.54],  // Jammu and Kashmir
  'KA': [75.67, 15.71],  // Karnataka
  'KL': [76.87, 9.32],  // Kerala
  'LA': [77.44, 34.03],  // Ladakh
  'LD': [73.05, 8.26],  // Lakshadweep
  'MH': [75.28, 19.38],  // Maharashtra
  'ML': [90.42, 25.58],  // Meghalaya
  'MN': [93.77, 24.62],  // Manipur
  'MP': [79.82, 23.12],  // Madhya Pradesh
  'MZ': [92.85, 23.55],  // Mizoram
  'NL': [94.62, 26.13],  // Nagaland
  'OR': [84.58, 20.88],  // Odisha
  'PB': [75.49, 30.72],  // Punjab
  'PY': [79.8, 10.93],  // Puducherry
  'RJ': [73.9, 26.97],  // Rajasthan
  'SK': [88.41, 27.5],  // Sikkim
  'TG': [78.98, 17.9],  // Telangana
  'TN': [78.28, 10.91],  // Tamil Nadu
  'TR': [91.55, 23.65],  // Tripura
  'UP': [80.49, 26.91],  // Uttar Pradesh
  'UT': [79.46, 30.07],  // Uttarakhand
  'WB': [87.83, 23.23],  // West Bengal
};

/**
 * The GeoJSON uses ISO 3166-2 subdivision codes. Models (and older data) reach
 * for other spellings of the same state, so normalise before matching.
 */
const CODE_ALIASES: Record<string, string> = {
  OD: 'OR',   // Odisha — ISO says OR, most datasets say OD
  ORI: 'OR',
  UK: 'UT',   // Uttarakhand — commonly UK
  UA: 'UT',
  CG: 'CT',   // Chhattisgarh — commonly CG
  TS: 'TG',   // Telangana — commonly TS
  PN: 'PB',   // Punjab
  DD: 'DH',   // Daman & Diu, merged into Dadra & Nagar Haveli in 2020
  DN: 'DH',
  PO: 'PY',   // Puducherry
  ND: 'DL',   // Delhi / NCT
};

/** Normalise a region code from the agent to the code used in the GeoJSON. */
export function normalizeRegionCode(code: string): string {
  if (!code) return '';
  // Accept full ISO 3166-2 form ("IN-GJ") as well as the bare subdivision code.
  const bare = code.trim().toUpperCase().replace(/^IN[-_]/, '');
  return CODE_ALIASES[bare] ?? bare;
}

/** Label anchor for a region code, or null when the code is unknown. */
export function getRegionCentroid(code: string): [number, number] | null {
  return STATE_CENTROIDS[normalizeRegionCode(code)] ?? null;
}

/** Display names for Indian admin-1 units, keyed by normalised code. */
export const STATE_NAMES: Record<string, string> = {
  AN: 'Andaman & Nicobar', AP: 'Andhra Pradesh', AR: 'Arunachal Pradesh', AS: 'Assam',
  BR: 'Bihar', CH: 'Chandigarh', CT: 'Chhattisgarh', DH: 'Dadra & Nagar Haveli',
  DL: 'Delhi', GA: 'Goa', GJ: 'Gujarat', HP: 'Himachal Pradesh', HR: 'Haryana',
  JH: 'Jharkhand', JK: 'Jammu & Kashmir', KA: 'Karnataka', KL: 'Kerala', LA: 'Ladakh',
  LD: 'Lakshadweep', MH: 'Maharashtra', ML: 'Meghalaya', MN: 'Manipur', MP: 'Madhya Pradesh',
  MZ: 'Mizoram', NL: 'Nagaland', OR: 'Odisha', OD: 'Odisha', PB: 'Punjab', PY: 'Puducherry',
  RJ: 'Rajasthan', SK: 'Sikkim', TG: 'Telangana', TN: 'Tamil Nadu', TR: 'Tripura',
  UP: 'Uttar Pradesh', UT: 'Uttarakhand', UK: 'Uttarakhand', WB: 'West Bengal',
  IN: 'India',
};

/** Human-readable name for a region code, falling back to the code itself. */
export function getRegionName(code: string): string {
  const bare = normalizeRegionCode(code);
  return STATE_NAMES[bare] ?? code;
}
