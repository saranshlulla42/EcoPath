/**
 * Movebank service.
 *
 * Movebank blocks browser-origin requests, so this has always gone through the
 * backend. It now uses the unified /api/data/telemetry/* routes, which share
 * the same retry, caching and fallback behaviour as every other source.
 */

import { getTelemetryStudies, getTelemetryTracksUnified } from "./dataClient";

export interface MovebankStudy {
  id: number;
  name: string;
  taxonIds: string;
  numberOfIndividuals?: number;
  studyType?: string;
  sensorTypeIds?: string;
}

export interface TelemetryTrack {
  path: [number, number][];
  timestamps: number[];
  individualId: string;
}

export async function getStudiesForSpecies(
  scientificName: string
): Promise<MovebankStudy[]> {
  try {
    return await getTelemetryStudies(scientificName);
  } catch (err) {
    console.warn("[movebank] study lookup failed:", err);
    return [];
  }
}

export async function getTelemetryTracks(studyId: number): Promise<TelemetryTrack[]> {
  try {
    return await getTelemetryTracksUnified(studyId);
  } catch (err) {
    console.warn("[movebank] track lookup failed:", err);
    return [];
  }
}
