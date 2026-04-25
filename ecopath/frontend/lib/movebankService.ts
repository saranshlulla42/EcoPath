import axios from "axios";
import type { MovebankStudy, MovebankTrack } from "./types";

// ── Movebank API Client ────────────────────────────────────────────────────
// Routes through backend API proxy to avoid CORS issues and enable server-side
// rate limiting. Backend handles retries and caching.

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 35000, // Longer timeout for server-side retries
});

/**
 * Fetch studies tagged with a given species name.
 */
export async function getStudiesForSpecies(
  taxonName: string
): Promise<MovebankStudy[]> {
  const cacheKey = `movebank_studies_${taxonName}`;
  if (typeof sessionStorage !== "undefined") {
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) return JSON.parse(cached);
  }

  try {
    const resp = await apiClient.get("/api/movebank/studies", {
      params: { taxon_name: taxonName },
    });

    const studies = resp.data.studies || [];
    const finalStudies = studies.map((s: any) => ({
      id: s.id ?? 0,
      name: s.name ?? "Unnamed Study",
      taxonIds: s.taxonIds ?? "",
      numberOfIndividuals: s.numberOfIndividuals,
      studyType: s.studyType,
      sensorType: s.sensorTypeIds,
    }));

    if (typeof sessionStorage !== "undefined") {
      try {
        sessionStorage.setItem(cacheKey, JSON.stringify(finalStudies));
      } catch {} // ignore quota errors
    }
    return finalStudies;
  } catch (err) {
    console.warn("[Movebank] Failed to fetch studies for:", taxonName, err);
    return [];
  }
}

/**
 * Fetch the GPS track for a study as Deck.gl TripsLayer-ready data.
 * Sorted ascending by timestamp.
 *
 * Returns array of tracks, one per individual animal in the study.
 */
export async function getTelemetryTracks(
  studyId: number
): Promise<MovebankTrack[]> {
  const cacheKey = `movebank_${studyId}`;
  if (typeof sessionStorage !== "undefined") {
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) return JSON.parse(cached);
  }

  try {
    const resp = await apiClient.get("/api/movebank/tracks", {
      params: { study_id: studyId },
    });

    const tracks = resp.data.tracks || [];
    const finalTracks = tracks.map((t: any) => ({
      path: t.path,
      timestamps: t.timestamps,
      individualId: t.individualId,
    }));

    if (typeof sessionStorage !== "undefined") {
      try {
        sessionStorage.setItem(cacheKey, JSON.stringify(finalTracks));
      } catch {}
    }
    return finalTracks;
  } catch (err) {
    console.warn("[Movebank] Failed to fetch tracks for study:", studyId, err);
    return [];
  }
}
