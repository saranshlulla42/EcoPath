import axios from "axios";
import type { GBIFSearchResult } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const GBIF = "https://api.gbif.org/v1";

export const api = axios.create({
  baseURL: BASE,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// ── Species Search (live GBIF) ─────────────────────────────────────────────
export const searchSpecies = (q: string): Promise<GBIFSearchResult[]> =>
  axios
    .get(`${GBIF}/species/search`, {
      params: { q, rank: "SPECIES", higherTaxonKey: 212, limit: 10 },
    })
    .then((r) =>
      (r.data.results ?? [])
        .filter((s: any) => s.kingdom === "Animalia" && s.key)
        .map((s: any) => ({
          gbif_key: s.key,
          common_name:
            s.vernacularNames?.[0]?.vernacularName ??
            s.canonicalName ??
            s.scientificName ??
            "Unknown",
          scientific_name: s.canonicalName ?? s.scientificName ?? "",
          family: s.family ?? undefined,
        }))
    );

// ── Species Detail (live GBIF) ─────────────────────────────────────────────
export const getGBIFSpeciesDetail = (gbifKey: string) =>
  axios.get(`${GBIF}/species/${gbifKey}`).then((r) => r.data);

export const getGBIFSpeciesMedia = (gbifKey: string) =>
  axios
    .get(`${GBIF}/species/${gbifKey}/media`, { params: { limit: 5 } })
    .then((r) => r.data.results ?? []);

export const getGBIFOccurrences = (
  gbifKey: string,
  country: string = "IN",
  params: Record<string, string | number | boolean> = {}
) => {
  const queryParams: Record<string, string | number | boolean> = {
    taxonKey: gbifKey,
    hasCoordinate: true,
    limit: 300,
    ...params,
  };
  if (country && country !== "GLOBAL") queryParams.country = country;
  return axios.get(`${GBIF}/occurrence/search`, { params: queryParams }).then((r) => r.data);
};

// ── Maps (direct GBIF) ─────────────────────────────────────────────────────

/**
 * Spatial-bin occurrence points into a ~0.5° grid for density-weighted heatmap.
 * Each bin becomes a single GeoJSON point with an aggregated `count`.
 */
function binOccurrences(
  results: any[],
  resolution: number = 0.5
): GeoJSON.FeatureCollection {
  const bins = new Map<string, { lat: number; lng: number; count: number; states: Set<string>; year: number }>();

  for (const occ of results) {
    const lat = occ.decimalLatitude;
    const lng = occ.decimalLongitude;
    if (lat == null || lng == null) continue;

    // Snap to grid cell center
    const binLat = Math.round(lat / resolution) * resolution;
    const binLng = Math.round(lng / resolution) * resolution;
    const key = `${binLat},${binLng}`;

    const existing = bins.get(key);
    if (existing) {
      existing.count++;
      if (occ.stateProvince) existing.states.add(occ.stateProvince);
    } else {
      const states = new Set<string>();
      if (occ.stateProvince) states.add(occ.stateProvince);
      bins.set(key, { lat: binLat, lng: binLng, count: 1, states, year: occ.year ?? 0 });
    }
  }

  const features: GeoJSON.Feature[] = Array.from(bins.values()).map((b) => ({
    type: "Feature" as const,
    geometry: { type: "Point" as const, coordinates: [b.lng, b.lat] },
    properties: {
      count: b.count,
      state: [...b.states].join(", ") || "Unknown",
      year: b.year,
    },
  }));

  return { type: "FeatureCollection", features };
}

/**
 * Fetch occurrence data from GBIF for a species and build a density heatmap.
 * Returns GeoJSON FeatureCollection with aggregated bin counts.
 * Pass country as an ISO 3166-1 alpha-2 code (e.g. "IN", "US") to filter by country,
 * or omit / pass "GLOBAL" for worldwide data.
 */
export const getGBIFHeatmapData = async (
  gbifKey: string | number,
  year?: number,
  country?: string
): Promise<{
  geojson: GeoJSON.FeatureCollection;
  total_points: number;
  max_count: number;
  total_records: number;
}> => {
  const params: Record<string, string | number | boolean> = {
    taxonKey: gbifKey,
    hasCoordinate: true,
    limit: 300,
  };
  if (country && country !== "GLOBAL") params.country = country;
  if (year) params.year = year;

  const resp = await axios.get(`${GBIF}/occurrence/search`, { params });
  const results = resp.data.results ?? [];
  const geojson = binOccurrences(results);
  const counts = geojson.features.map((f) => (f.properties as any)?.count ?? 1);

  return {
    geojson,
    total_points: geojson.features.length,
    max_count: counts.length > 0 ? Math.max(...counts) : 0,
    total_records: resp.data.count ?? results.length,
  };
};

/**
 * Fetch per-year occurrence counts using GBIF facets — single API call.
 * Returns a timeline object: { [year]: { total, states } }
 * Pass country as an ISO 3166-1 alpha-2 code (e.g. "IN", "US") to filter by country,
 * or omit / pass "GLOBAL" for worldwide data.
 */
export const getGBIFHeatmapTimeline = async (
  gbifKey: string | number,
  country?: string
): Promise<{ timeline: Record<number, { total: number; states: number }> }> => {
  const queryParams: Record<string, string | number | boolean> = {
    taxonKey: gbifKey,
    hasCoordinate: true,
    limit: 0,
    facet: "year",
    facetLimit: 20,
  };
  if (country && country !== "GLOBAL") queryParams.country = country;
  const resp = await axios.get(`${GBIF}/occurrence/search`, {
    params: queryParams,
  });

  const timeline: Record<number, { total: number; states: number }> = {};
  const yearFacet = (resp.data.facets ?? []).find((f: any) => f.field === "YEAR");
  if (yearFacet) {
    for (const item of yearFacet.counts ?? []) {
      const yr = parseInt(item.name, 10);
      if (!isNaN(yr)) {
        timeline[yr] = { total: item.count, states: 0 };
      }
    }
  }

  // Fill missing years in 2014–2024 range with 0
  for (let yr = 2014; yr <= 2024; yr++) {
    if (!timeline[yr]) timeline[yr] = { total: 0, states: 0 };
  }

  return { timeline };
};

export const getMigrationRoutes = (speciesId: string) =>
  api.get(`/api/maps/migration/${speciesId}`).then((r) => r.data);

// ── Anomalies ──────────────────────────────────────────────────────────────
export const getAnomalies = (speciesId: string) =>
  api.get(`/api/anomalies/${speciesId}`).then((r) => r.data);

// ── Chat (SSE streaming) ───────────────────────────────────────────────────
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ExtinctionRiskReportRequest {
  species_name: string;
  gbif_key?: number;
  country_code?: string;
  language?: string;
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

export interface ExtinctionRiskReportResponse {
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

export const createExtinctionRiskReport = (payload: ExtinctionRiskReportRequest) =>
  api.post<ExtinctionRiskReportResponse>("/api/extinction-risk/report", payload, {
    timeout: 360000,
  }).then((r) => r.data);

export async function* streamChat(
  messages: ChatMessage[],
  speciesContext?: string,
  yearContext?: number
): AsyncGenerator<string> {
  const resp = await fetch(`${BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages,
      species_context: speciesContext,
      year_context: yearContext,
    }),
  });

  if (!resp.ok) throw new Error(`Chat error: ${resp.status}`);
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const payload = JSON.parse(line.slice(6));
        if (payload.delta) yield payload.delta;
        if (payload.done) return;
      } catch {
        /* skip malformed */
      }
    }
  }
}
