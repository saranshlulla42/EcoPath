/**
 * Unified data client.
 *
 * Every external source now reaches the browser through the backend's
 * /api/data/* surface. Calling GBIF and eBird directly from here meant the
 * eBird API key shipped in the client bundle, responses could not be cached
 * across users, and the app was exposed to upstream CORS and rate-limit
 * behaviour it could not control.
 *
 * Responses carry provenance so the UI can attribute a figure to its source.
 */

import axios from "axios";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const dataApi = axios.create({
  baseURL: `${BASE}/api/data`,
  timeout: 60000,
  headers: { "Content-Type": "application/json" },
});

export interface Provenance {
  source: string;
  operation: string;
  fetched_at: number;
  age_seconds: number;
  cached: boolean;
  upstream_url: string | null;
  degraded: boolean;
  note: string | null;
}

export interface Envelope<T> {
  data: T;
  provenance: Provenance;
}

/**
 * A failed data request, carrying enough context to act on.
 *
 * Axios rejects with "Request failed with status code 502", which says nothing
 * about which source failed or why. The backend already sends a useful `detail`
 * (for example "eBird returned 400"); this surfaces it instead of discarding it.
 */
export class DataError extends Error {
  readonly status: number | null;
  readonly path: string;
  readonly detail: string | null;
  /** True when the backend could not reach the upstream source at all. */
  readonly upstreamUnavailable: boolean;

  constructor(path: string, status: number | null, detail: string | null) {
    super(detail ? `${path}: ${detail}` : `${path}: request failed`);
    this.name = "DataError";
    this.path = path;
    this.status = status;
    this.detail = detail;
    this.upstreamUnavailable = status === 502 || status === 503 || status === null;
  }
}

function toDataError(path: string, err: unknown): DataError {
  if (axios.isAxiosError(err)) {
    const detail =
      (err.response?.data as { detail?: string } | undefined)?.detail ?? err.message;
    return new DataError(path, err.response?.status ?? null, detail);
  }
  return new DataError(path, null, err instanceof Error ? err.message : String(err));
}

/** Fetch keeping provenance, for UI that shows where a figure came from. */
export async function withProvenance<T>(
  path: string,
  params?: Record<string, unknown>
): Promise<Envelope<T>> {
  try {
    const resp = await dataApi.get<Envelope<T>>(path, { params });
    return resp.data;
  } catch (err) {
    throw toDataError(path, err);
  }
}

/** Unwrap an envelope, discarding provenance. Throws `DataError` on failure. */
async function unwrap<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const envelope = await withProvenance<T>(path, params);
  return envelope.data;
}

/**
 * Unwrap, falling back instead of throwing.
 *
 * Use where a view should still render when one source is down — the previous
 * browser-side eBird client degraded this way, and moving the call server-side
 * should not turn a quiet empty result into a crashed page.
 */
async function unwrapOr<T>(
  path: string,
  fallback: T,
  params?: Record<string, unknown>
): Promise<T> {
  try {
    return await unwrap<T>(path, params);
  } catch (err) {
    const reason = err instanceof DataError ? err.message : String(err);
    console.warn(`[data] ${reason} — falling back`);
    return fallback;
  }
}

// ── Species ────────────────────────────────────────────────────────────────

export const searchSpeciesUnified = (q: string, limit = 20) =>
  unwrap<any[]>("/species/search", { q, limit });

export const getSpeciesDetail = (gbifKey: string | number) =>
  unwrap<any>(`/species/${gbifKey}/detail`);

export const getSpeciesMedia = (gbifKey: string | number, limit = 5) =>
  unwrap<any[]>(`/species/${gbifKey}/media`, { limit });

// ── Occurrences ────────────────────────────────────────────────────────────

export const getOccurrencePoints = (gbifKey: string | number, year: number, limit = 300) =>
  unwrap<Array<{ lat: number; lng: number; year: number; month: number | null; state: string }>>(
    `/occurrences/${gbifKey}/points`,
    { year, limit }
  );

export const getOccurrenceTimeline = (
  gbifKey: string | number,
  yearStart = 2015,
  yearEnd = 2024,
  country: string | null = "IN"
) =>
  unwrap<Array<{ year: number; count: number }>>(`/occurrences/${gbifKey}/timeline`, {
    year_start: yearStart,
    year_end: yearEnd,
    ...(country && country !== "GLOBAL" ? { country } : { country: "" }),
  });

// ── eBird ──────────────────────────────────────────────────────────────────

export interface UnifiedObservation {
  lat: number;
  lng: number;
  date: string;
  count: number;
  species_code: string;
  species_name: string;
  location_name: string;
}

export const getEBirdObservations = (speciesCode: string, back = 30, regions?: string[]) =>
  unwrapOr<UnifiedObservation[]>(`/ebird/observations/${speciesCode}`, [], {
    back,
    ...(regions?.length ? { regions: regions.join(",") } : {}),
  });

export const getEBirdSeasonal = (speciesCode: string, year: number) =>
  unwrapOr<Record<string, UnifiedObservation[]>>(`/ebird/seasonal/${speciesCode}`, {}, { year });

/**
 * Throws on failure rather than degrading: the migration view is unusable
 * without a species list, and a silent empty array renders as "0 species
 * tracked", which is indistinguishable from eBird being down.
 */
export const getEBirdTaxonomy = (orders?: string[]) =>
  unwrap<Array<{ species_code: string; common_name: string; scientific_name: string; order: string }>>(
    "/ebird/taxonomy",
    orders?.length ? { orders: orders.join(",") } : undefined
  );

// ── Telemetry ──────────────────────────────────────────────────────────────

export const getTelemetryStudies = (taxonName: string) =>
  unwrapOr<any[]>("/telemetry/studies", [], { taxon_name: taxonName });

export const getTelemetryTracksUnified = (studyId: number) =>
  unwrapOr<any[]>("/telemetry/tracks", [], { study_id: studyId });

// ── Media, environment, evidence ───────────────────────────────────────────

export const getBirdCall = (scientificName: string, country = "india") =>
  unwrap<any>(`/audio/${encodeURIComponent(scientificName)}`, { country });

export const birdCallAudioUrl = (recordingId: string) =>
  `${BASE}/api/data/audio/recording/${recordingId}`;

export const getWeather = (lat: number, lng: number, year: number) =>
  unwrap<any>("/weather", { lat, lng, year });

export const getConservationStatus = (scientificName: string) =>
  unwrap<any>(`/evidence/status/${encodeURIComponent(scientificName)}`);

export const getSpeciesContext = (scientificName: string, commonName = "") =>
  unwrap<{ title: string; extract: string; thumbnail: string | null; url: string }>(
    `/evidence/context/${encodeURIComponent(scientificName)}`,
    commonName ? { common_name: commonName } : undefined
  );

// ── Introspection ──────────────────────────────────────────────────────────

export const getDataSources = () =>
  dataApi.get<{ sources: Record<string, any>; cache: any }>("/sources").then((r) => r.data);

// ── Vision ─────────────────────────────────────────────────────────────────

export interface BirdIdentification {
  is_bird: boolean;
  is_real_photo?: boolean;
  identified?: boolean;
  scientific_name: string | null;
  common_name?: string | null;
  confidence: number;
  reasoning?: string;
  gbif_key: number | null;
}

/**
 * Identify a bird from a photo.
 *
 * Runs entirely server-side: the model call and the GBIF lookup both happen in
 * the backend, so no provider key reaches the browser.
 */
export async function identifyBird(file: File): Promise<BirdIdentification> {
  const form = new FormData();
  form.append("image", file);
  try {
    const resp = await dataApi.post<Envelope<BirdIdentification>>("/vision/identify", form, {
      // Content-Type must be unset so the browser generates it *with* the
      // multipart boundary. Sending "multipart/form-data" by hand omits the
      // boundary and the server rejects the body outright.
      headers: { "Content-Type": undefined },
      timeout: 120000,
    });
    return resp.data.data;
  } catch (err) {
    throw toDataError("/vision/identify", err);
  }
}
