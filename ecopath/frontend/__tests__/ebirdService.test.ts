import { describe, it, expect } from "vitest";
import { normalizeObservation } from "../lib/ebirdService";

describe("normalizeObservation", () => {
  it("normalises a complete eBird API response object", () => {
    const raw = {
      speciesCode: "bartgo",
      comName: "Bar-tailed Godwit",
      sciName: "Limosa lapponica",
      locName: "Miranda Shorebird Centre",
      lat: -37.203,
      lng: 175.463,
      obsDt: "2024-03-15 08:30",
      howMany: 42,
    };

    const result = normalizeObservation(raw);
    expect(result).toEqual({
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
    const raw = {};
    const result = normalizeObservation(raw);
    expect(result).toEqual({
      lat: 0,
      lng: 0,
      date: "",
      count: 1,
      speciesCode: "",
      speciesName: "Unknown",
      locationName: "Unknown",
    });
  });

  it("defaults count to 1 when howMany is not a number", () => {
    const raw = { howMany: "X" };
    const result = normalizeObservation(raw);
    expect(result.count).toBe(1);
  });

  it("uses sciName as fallback when comName is missing", () => {
    const raw = { sciName: "Limosa lapponica" };
    const result = normalizeObservation(raw);
    expect(result.speciesName).toBe("Limosa lapponica");
  });

  it("preserves negative coordinates (southern/western hemisphere)", () => {
    const raw = { lat: -45.5, lng: -122.3 };
    const result = normalizeObservation(raw);
    expect(result.lat).toBe(-45.5);
    expect(result.lng).toBe(-122.3);
  });

  it("handles zero count correctly", () => {
    const raw = { howMany: 0 };
    const result = normalizeObservation(raw);
    expect(result.count).toBe(0);
  });
});
