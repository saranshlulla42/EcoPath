import axios from "axios";
import type { GBIFSearchResult } from "./types";
import {
  getOccurrencePoints,
  getOccurrenceTimeline,
  getSpeciesDetail,
  getSpeciesMedia,
  searchSpeciesUnified,
} from "./dataClient";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: BASE,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// ── Species ────────────────────────────────────────────────────────────────
// These used to hit https://api.gbif.org/v1 straight from the browser. They now
// go through the backend's unified data layer, which caches across users and
// keeps upstream credentials and rate limits server-side.

export const searchSpecies = async (q: string): Promise<GBIFSearchResult[]> => {
  const rows = await searchSpeciesUnified(q, 10);
  return rows.map((s: any) => ({
    gbif_key: s.gbif_key ?? s.key,
    common_name: s.common_name ?? s.scientific_name ?? "Unknown",
    scientific_name: s.scientific_name ?? "",
    family: s.family ?? undefined,
  }));
};

export const getGBIFSpeciesDetail = (gbifKey: string) => getSpeciesDetail(gbifKey);

export const getGBIFSpeciesMedia = (gbifKey: string) => getSpeciesMedia(gbifKey, 5);

export const getGBIFOccurrences = async (
  gbifKey: string,
  country: string = "IN",
  params: Record<string, string | number | boolean> = {}
) => {
  const year = typeof params.year === "number" ? params.year : new Date().getFullYear();
  const limit = typeof params.limit === "number" ? params.limit : 300;
  const points = await getOccurrencePoints(gbifKey, year, limit);
  // Shaped like the GBIF occurrence/search payload the callers expect.
  return {
    results: points.map((p) => ({
      decimalLatitude: p.lat,
      decimalLongitude: p.lng,
      year: p.year,
      month: p.month,
      stateProvince: p.state,
    })),
    count: points.length,
  };
};

// ── Maps ───────────────────────────────────────────────────────────────────

/**
 * Spatial-bin occurrence points into a ~0.5° grid for a density-weighted heatmap.
 * Each bin becomes one GeoJSON point carrying an aggregated `count`.
 */
function binOccurrences(
  points: Array<{ lat: number; lng: number; year: number; state: string }>,
  resolution = 0.5
): GeoJSON.FeatureCollection {
  const bins = new Map<
    string,
    { lat: number; lng: number; count: number; states: Set<string>; year: number }
  >();

  for (const p of points) {
    if (typeof p.lat !== "number" || typeof p.lng !== "number") continue;
    const binLat = Math.round(p.lat / resolution) * resolution;
    const binLng = Math.round(p.lng / resolution) * resolution;
    const key = `${binLat},${binLng}`;

    const existing = bins.get(key);
    if (existing) {
      existing.count += 1;
      if (p.state) existing.states.add(p.state);
    } else {
      const states = new Set<string>();
      if (p.state) states.add(p.state);
      bins.set(key, { lat: binLat, lng: binLng, count: 1, states, year: p.year });
    }
  }

  const features: GeoJSON.Feature[] = Array.from(bins.values()).map((b) => ({
    type: "Feature",
    geometry: { type: "Point", coordinates: [b.lng, b.lat] },
    properties: {
      count: b.count,
      year: b.year,
      states: Array.from(b.states),
    },
  }));

  return { type: "FeatureCollection", features };
}

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
  const points = await getOccurrencePoints(gbifKey, year ?? new Date().getFullYear(), 300);
  const geojson = binOccurrences(points);
  const counts = geojson.features.map((f) => (f.properties as any)?.count ?? 1);

  return {
    geojson,
    total_points: geojson.features.length,
    max_count: counts.length > 0 ? Math.max(...counts) : 0,
    total_records: points.length,
  };
};

export const getGBIFHeatmapTimeline = async (
  gbifKey: string | number,
  country?: string
): Promise<{ timeline: Record<number, { total: number; states: number }> }> => {
  const series = await getOccurrenceTimeline(gbifKey, 2014, 2024, country ?? "IN");

  const timeline: Record<number, { total: number; states: number }> = {};
  for (const point of series) {
    timeline[point.year] = { total: point.count, states: 0 };
  }
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
  draft_for_review?: boolean;
  validation_status?: string;
  validation_errors?: string[];
  missing_evidence_fields?: string[];
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
