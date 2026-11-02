import { describe, it, expect } from "vitest";
import { normalizeObservation } from "../lib/ebirdService";
import type { UnifiedObservation } from "../lib/dataClient";

/**
 * Raw eBird records are now normalised server-side (see
 * backend/tests/test_ebird_normalization.py). What this module owns is the
 * mapping from the backend's snake_case observation onto the camelCase shape
 * the UI components consume.
 */
describe("normalizeObservation", () => {
  it("maps a complete backend observation onto the UI shape", () => {
    const raw: UnifiedObservation = {
      lat: -37.203,
      lng: 175.463,
      date: "2024-03-15 08:30",
      count: 42,
      species_code: "bartgo",
      species_name: "Bar-tailed Godwit",
      location_name: "Miranda Shorebird Centre",
    };

    expect(normalizeObservation(raw)).toEqual({
      lat: -37.203,
      lng: 175.463,
      date: "2024-03-15 08:30",
      count: 42,
      speciesCode: "bartgo",
      speciesName: "Bar-tailed Godwit",
      locationName: "Miranda Shorebird Centre",
    });
  });

  it("defaults missing fields gracefully", () => {
    expect(normalizeObservation({} as UnifiedObservation)).toEqual({
      lat: 0,
      lng: 0,
      date: "",
      count: 1,
      speciesCode: "",
      speciesName: "Unknown",
      locationName: "Unknown",
    });
  });

  it("preserves negative coordinates (southern/western hemisphere)", () => {
    const result = normalizeObservation({ lat: -45.5, lng: -122.3 } as UnifiedObservation);
    expect(result.lat).toBe(-45.5);
    expect(result.lng).toBe(-122.3);
  });

  it("preserves a surveyed zero count", () => {
    const result = normalizeObservation({ count: 0 } as UnifiedObservation);
    expect(result.count).toBe(0);
  });
});
