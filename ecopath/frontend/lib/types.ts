export interface Species {
  id?: string;
  gbif_key: number;
  common_name: string;
  scientific_name: string;
  family?: string;
  order_name?: string;
  iucn_status?: string;
  endemic_india: boolean;
  migratory: boolean;
  primary_habitat: string[];
  primary_range: string[];
  image_url?: string;
  gbif_image_url?: string;
  xeno_canto_id?: string;
  description?: string;
  fun_fact?: string;
}

/** Lightweight result from GBIF species/search used in the autocomplete dropdown */
export interface GBIFSearchResult {
  gbif_key: number;
  common_name: string;
  scientific_name: string;
  family?: string;
}

export interface PopulationYearSummary {
  year: number;
  total_observations: number;
  states_observed: number;
  rolling_avg_5yr?: number;
}

export interface Anomaly {
  id: string;
  species_id: string;
  year: number;
  anomaly_type: "surge" | "dip" | "local_extinction" | "recolonization";
  magnitude_pct?: number;
  severity?: "low" | "medium" | "high" | "critical";
  affected_state?: string;
  observed_count?: number;
  expected_count?: number;
  rolling_avg_5yr?: number;
  causal_hypothesis?: string;
  weather_context?: Record<string, unknown>;
  detected_at?: string;
}

export interface Waypoint {
  lat: number;
  lng: number;
  month: number;
  location_name: string;
  description?: string;
}

export interface MigrationRoute {
  id: string;
  route_name: string;
  flyway?: string;
  season: string;
  direction?: string;
  waypoints: Waypoint[];
  active_months: number[];
  distance_km?: number;
  geojson?: GeoJSON.Feature;
}

export interface XenoCantoRecording {
  id: string;
  common_name: string;
  country: string;
  location?: string;
  quality: string;
  duration?: string;
  audio_url: string;
  sonogram_url?: string;
  recordist?: string;
  date?: string;
}

export interface SpeciesDetail extends Species {
  population_history: PopulationYearSummary[];
  anomalies: Anomaly[];
  migration_routes: MigrationRoute[];
  xeno_canto_recording?: XenoCantoRecording;
}

export interface VisionIDResult {
  identified: boolean;
  common_name?: string;
  scientific_name?: string;
  confidence: number;
  is_bird: boolean;
  is_real_photo: boolean;
  spoof_warning?: string;
  matched_species?: Species;
  reasoning: string;
}

export interface HeatmapResponse {
  geojson: GeoJSON.FeatureCollection;
  total_points: number;
  max_count: number;
  total_records: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ExtinctionRiskReportEvidenceItem {
  query: string;
  title: string;
  url: string;
  snippet: string;
  source?: string;
  seendate?: string;
  language?: string;
}

export interface ExtinctionRiskReportResult {
  species: {
    gbif_key?: number | null;
    common_name: string;
    scientific_name: string;
    family?: string | null;
    order_name?: string | null;
    iucn_status?: string | null;
    population_trend?: string | null;
    population_size?: string | null;
    habitat: string[];
    range_summary: string[];
    diet?: string | null;
    breeding_behavior?: string | null;
    migratory_behavior?: string | null;
    source_urls: string[];
  };
  current_conservation_status: string;
  key_threats: string[];
  survivability_assessment: string;
  mitigation_actions: string[];
  sources: ExtinctionRiskReportEvidenceItem[];
  limited_evidence_reasons: string[];
  reviewer_notes: string;
  decision_support_draft: string;
  model_name: string;
  generation_mode: string;
  model_output_status: string;
  evidence_items_reviewed: number;
  disclaimer: string;
}

// ── Migration Visualization Types ──────────────────────────────────────────

/** Normalised eBird observation — consistent shape for all internal use */
export interface EBirdObservation {
  lat: number;
  lng: number;
  date: string;
  count: number;
  speciesCode: string;
  speciesName: string;
  locationName: string;
}

/** Movebank study metadata */
export interface MovebankStudy {
  id: number;
  name: string;
  taxonIds: string;
  numberOfIndividuals?: number;
  studyType?: string;
  sensorType?: string;
}

/** Deck.gl TripsLayer-ready telemetry track */
export interface MovebankTrack {
  path: [number, number][]; // [lng, lat][]
  timestamps: number[];      // epoch_ms[]
  individualId?: string;
}

/** Species info card for the migration panel */
export interface MigrationSpeciesInfo {
  speciesCode: string;
  commonName: string;
  scientificName: string;
  totalDistanceKm?: number;
  originRegion?: string;
  destinationRegion?: string;
  activeMonths?: number[];
  dataSource: "ebird" | "movebank" | "both";
  color: string; // hex color for map rendering
}
