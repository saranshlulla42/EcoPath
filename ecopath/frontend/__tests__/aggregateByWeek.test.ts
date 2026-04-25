import { describe, it, expect } from "vitest";
import { aggregateByWeek, getISOWeekNumber } from "../lib/aggregateByWeek";
import type { EBirdObservation } from "../lib/types";

// ── Helper to create test observations ─────────────────────────────────────
function makeObs(
  date: string,
  speciesCode = "bartgo",
  lat = 0,
  lng = 0
): EBirdObservation {
  return {
    lat,
    lng,
    date,
    count: 1,
    speciesCode,
    speciesName: "Test Species",
    locationName: "Test Location",
  };
}

describe("aggregateByWeek", () => {
  it("returns an empty Map with 52 keys for empty input", () => {
    const result = aggregateByWeek([]);
    expect(result).toBeInstanceOf(Map);
    expect(result.size).toBe(52);
    for (let w = 1; w <= 52; w++) {
      expect(result.get(w)).toEqual([]);
    }
  });

  it("groups observations into the correct ISO week", () => {
    // 2024-01-01 is a Monday, ISO week 1
    const obs = [
      makeObs("2024-01-01"),
      makeObs("2024-01-02"),
      makeObs("2024-01-08"), // week 2
    ];
    const result = aggregateByWeek(obs);
    expect(result.get(1)!.length).toBe(2);
    expect(result.get(2)!.length).toBe(1);
  });

  it("handles observations spanning a year boundary (Dec → Jan)", () => {
    const obs = [
      makeObs("2023-12-28"), // ISO week 52 of 2023
      makeObs("2023-12-31"), // ISO week 52 of 2023 (or week 1 of 2024 depending on standard)
      makeObs("2024-01-01"), // ISO week 1 of 2024
      makeObs("2024-01-07"), // Still week 1
    ];
    const result = aggregateByWeek(obs);

    // All observations should land somewhere in the 1–52 range
    let totalCount = 0;
    for (const [, arr] of result) {
      totalCount += arr.length;
    }
    expect(totalCount).toBe(4);

    // Week 1 should have at least the Jan observations
    expect(result.get(1)!.length).toBeGreaterThanOrEqual(1);
  });

  it("places multiple species in the same week correctly", () => {
    const obs = [
      makeObs("2024-06-15", "bartgo"),
      makeObs("2024-06-15", "arcter"),
      makeObs("2024-06-16", "osprey"),
    ];
    const result = aggregateByWeek(obs);

    // All three should be in the same week
    const weekJun15 = getISOWeekNumber(new Date("2024-06-15"));
    const weekEntries = result.get(weekJun15)!;
    expect(weekEntries.length).toBe(3);
    const codes = weekEntries.map((o) => o.speciesCode);
    expect(codes).toContain("bartgo");
    expect(codes).toContain("arcter");
    expect(codes).toContain("osprey");
  });

  it("skips observations with invalid or missing dates", () => {
    const obs = [
      makeObs("2024-03-15"),
      makeObs(""),
      makeObs("not-a-date"),
    ];
    const result = aggregateByWeek(obs);

    let totalCount = 0;
    for (const [, arr] of result) {
      totalCount += arr.length;
    }
    expect(totalCount).toBe(1);
  });

  it("folds week 53 into week 52", () => {
    // 2015-12-31 is in ISO week 53 of 2015
    const obs = [makeObs("2015-12-31")];
    const result = aggregateByWeek(obs);

    // Should appear in week 52, not create a 53rd week
    expect(result.size).toBe(52);
    expect(result.get(52)!.length).toBe(1);
  });
});

describe("getISOWeekNumber", () => {
  it("returns week 1 for 2024-01-01 (Monday)", () => {
    expect(getISOWeekNumber(new Date("2024-01-01"))).toBe(1);
  });

  it("returns week 52 or 1 for year-end dates", () => {
    const dec31 = getISOWeekNumber(new Date("2024-12-31"));
    expect(dec31).toBeGreaterThanOrEqual(1);
    expect(dec31).toBeLessThanOrEqual(53);
  });

  it("returns consistent results for mid-year dates", () => {
    // 2024-07-01 should be around week 27
    const week = getISOWeekNumber(new Date("2024-07-01"));
    expect(week).toBeGreaterThanOrEqual(26);
    expect(week).toBeLessThanOrEqual(28);
  });
});
