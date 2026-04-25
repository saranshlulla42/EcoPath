import type { EBirdObservation } from "./types";

/**
 * Compute origin (breeding) and destination (wintering) centroids from weekly observation data.
 * Origin = centroid of observations from the top 3 months by count (breeding/staging).
 * Destination = centroid of observations from the 3 months with lowest counts in the opposite half of the year.
 */
export function computeOriginDestination(
  weeklyMap: Map<number, EBirdObservation[]>
): {
  origin: { lat: number; lng: number } | null;
  destination: { lat: number; lng: number } | null;
} {
  const monthData: { count: number; lats: number[]; lngs: number[] }[] =
    Array.from({ length: 12 }, () => ({ count: 0, lats: [], lngs: [] }));

  for (const [week, obs] of weeklyMap) {
    const month = Math.min(11, Math.floor((week - 1) / (52 / 12)));
    for (const o of obs) {
      monthData[month].count += o.count || 1;
      monthData[month].lats.push(o.lat);
      monthData[month].lngs.push(o.lng);
    }
  }

  const ranked = monthData
    .map((d, i) => ({ ...d, month: i }))
    .filter((d) => d.lats.length > 0)
    .sort((a, b) => b.count - a.count);

  if (ranked.length < 2) return { origin: null, destination: null };

  // Top 3 months = origin (breeding grounds)
  const topMonths = ranked.slice(0, 3);
  const originLats = topMonths.flatMap((m) => m.lats);
  const originLngs = topMonths.flatMap((m) => m.lngs);
  const origin = {
    lat: originLats.reduce((a, b) => a + b, 0) / originLats.length,
    lng: originLngs.reduce((a, b) => a + b, 0) / originLngs.length,
  };

  // Opposite half of the year from top months
  const avgTopMonth =
    topMonths.reduce((a, m) => a + m.month, 0) / topMonths.length;
  const oppositeHalf = ranked.filter((m) => {
    const dist = Math.abs(m.month - avgTopMonth);
    const circularDist = Math.min(dist, 12 - dist);
    return circularDist >= 4;
  });

  // Bottom 3 from opposite half (lowest count)
  const bottomMonths = oppositeHalf.slice(-3);
  if (bottomMonths.length === 0) return { origin, destination: null };

  const destLats = bottomMonths.flatMap((m) => m.lats);
  const destLngs = bottomMonths.flatMap((m) => m.lngs);
  const destination = {
    lat: destLats.reduce((a, b) => a + b, 0) / destLats.length,
    lng: destLngs.reduce((a, b) => a + b, 0) / destLngs.length,
  };

  return { origin, destination };
}

/**
 * Compute season windows from weekly observation data.
 */
export function computeSeasonWindows(
  weeklyMap: Map<number, EBirdObservation[]>
): {
  breeding: [number, number] | null;
  migration: [number, number][];
  wintering: [number, number] | null;
} {
  const weekStats: { count: number; centroidLat: number }[] = [];
  let peakCount = 0;

  for (let w = 1; w <= 52; w++) {
    const obs = weeklyMap.get(w) ?? [];
    const count = obs.reduce((sum, o) => sum + (o.count || 1), 0);
    const avgLat =
      obs.length > 0
        ? obs.reduce((sum, o) => sum + o.lat, 0) / obs.length
        : 0;
    weekStats.push({ count, centroidLat: avgLat });
    if (count > peakCount) peakCount = count;
  }

  if (peakCount === 0)
    return { breeding: null, migration: [], wintering: null };

  const threshold = peakCount * 0.6;

  const activeLats = weekStats
    .filter((w) => w.count > 0)
    .map((w) => w.centroidLat);
  if (activeLats.length === 0)
    return { breeding: null, migration: [], wintering: null };
  const midLat = (Math.max(...activeLats) + Math.min(...activeLats)) / 2;

  type Season = "breeding" | "wintering" | "migration" | "inactive";
  const weekSeasons: Season[] = [];

  for (let w = 0; w < 52; w++) {
    const { count, centroidLat } = weekStats[w];
    if (count >= threshold && centroidLat > midLat) {
      weekSeasons.push("breeding");
    } else if (count >= threshold && centroidLat <= midLat) {
      weekSeasons.push("wintering");
    } else if (count > 0) {
      const prev = w > 0 ? weekStats[w - 1].centroidLat : centroidLat;
      const latShift = Math.abs(centroidLat - prev);
      if (latShift > 2) {
        weekSeasons.push("migration");
      } else if (count >= threshold * 0.3) {
        weekSeasons.push(centroidLat > midLat ? "breeding" : "wintering");
      } else {
        weekSeasons.push("inactive");
      }
    } else {
      weekSeasons.push("inactive");
    }
  }

  function findRange(season: Season): [number, number] | null {
    let start = -1,
      end = -1;
    let longestStart = -1,
      longestLen = 0;
    for (let i = 0; i < 52; i++) {
      if (weekSeasons[i] === season) {
        if (start === -1) start = i;
        end = i;
      } else {
        if (start !== -1 && end - start + 1 > longestLen) {
          longestLen = end - start + 1;
          longestStart = start;
        }
        start = -1;
      }
    }
    if (start !== -1 && end - start + 1 > longestLen) {
      longestLen = end - start + 1;
      longestStart = start;
    }
    return longestStart >= 0
      ? [longestStart + 1, longestStart + longestLen]
      : null;
  }

  function findMigrationRanges(): [number, number][] {
    const ranges: [number, number][] = [];
    let start = -1;
    for (let i = 0; i < 52; i++) {
      if (weekSeasons[i] === "migration") {
        if (start === -1) start = i;
      } else if (start !== -1) {
        ranges.push([start + 1, i]);
        start = -1;
      }
    }
    if (start !== -1) ranges.push([start + 1, 52]);
    return ranges;
  }

  return {
    breeding: findRange("breeding"),
    migration: findMigrationRanges(),
    wintering: findRange("wintering"),
  };
}

/**
 * Compute a point along a polyline at a given fraction (0–1) of total length.
 * coords is [lng, lat][].
 */
export function pointAlongLine(
  coords: [number, number][],
  fraction: number
): [number, number] {
  if (coords.length === 0) return [0, 0];
  if (coords.length === 1 || fraction <= 0) return coords[0];
  if (fraction >= 1) return coords[coords.length - 1];

  let totalLength = 0;
  const segLengths: number[] = [];
  for (let i = 0; i < coords.length - 1; i++) {
    const d = haversineDistance(
      coords[i][1],
      coords[i][0],
      coords[i + 1][1],
      coords[i + 1][0]
    );
    segLengths.push(d);
    totalLength += d;
  }

  if (totalLength === 0) return coords[0];

  const targetDist = fraction * totalLength;
  let accumulated = 0;

  for (let i = 0; i < segLengths.length; i++) {
    if (accumulated + segLengths[i] >= targetDist) {
      const segFraction = (targetDist - accumulated) / segLengths[i];
      return [
        coords[i][0] + segFraction * (coords[i + 1][0] - coords[i][0]),
        coords[i][1] + segFraction * (coords[i + 1][1] - coords[i][1]),
      ];
    }
    accumulated += segLengths[i];
  }

  return coords[coords.length - 1];
}

/**
 * Compute bearing (degrees, 0=north, clockwise) from point A to point B.
 */
export function computeBearing(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const lat1R = (lat1 * Math.PI) / 180;
  const lat2R = (lat2 * Math.PI) / 180;
  const y = Math.sin(dLng) * Math.cos(lat2R);
  const x =
    Math.cos(lat1R) * Math.sin(lat2R) -
    Math.sin(lat1R) * Math.cos(lat2R) * Math.cos(dLng);
  return (((Math.atan2(y, x) * 180) / Math.PI) + 360) % 360;
}

/**
 * Haversine distance in km.
 */
export function haversineDistance(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * Simple reverse geocode: map lat/lng to an approximate region name.
 * Uses a lightweight country-centroid lookup — no external API call.
 */
const REGION_CENTROIDS: [string, number, number, number][] = [
  // [name, lat, lng, radius_deg]
  ["Alaska", 64, -153, 10],
  ["Canada", 56, -96, 15],
  ["Greenland", 72, -40, 10],
  ["Iceland", 65, -18, 4],
  ["Norway", 62, 10, 6],
  ["Sweden", 62, 16, 5],
  ["Finland", 64, 26, 5],
  ["Russia", 60, 90, 30],
  ["UK", 54, -2, 4],
  ["France", 47, 2, 5],
  ["Spain", 40, -4, 5],
  ["Germany", 51, 10, 4],
  ["Italy", 43, 12, 4],
  ["Turkey", 39, 35, 6],
  ["Iran", 33, 53, 7],
  ["India", 22, 78, 12],
  ["China", 35, 105, 15],
  ["Japan", 36, 138, 5],
  ["Mongolia", 47, 103, 7],
  ["Kazakhstan", 48, 67, 10],
  ["Pakistan", 30, 69, 6],
  ["Afghanistan", 33, 65, 5],
  ["Saudi Arabia", 24, 45, 7],
  ["Egypt", 27, 30, 5],
  ["Sudan", 15, 30, 6],
  ["Ethiopia", 9, 39, 5],
  ["Kenya", 0, 38, 5],
  ["Tanzania", -6, 35, 5],
  ["South Africa", -29, 25, 7],
  ["Mozambique", -18, 35, 5],
  ["Madagascar", -19, 47, 5],
  ["Nigeria", 10, 8, 5],
  ["Ghana", 8, -1, 3],
  ["Senegal", 14, -14, 4],
  ["Morocco", 32, -6, 5],
  ["Algeria", 28, 3, 8],
  ["Libya", 27, 17, 7],
  ["DR Congo", -3, 23, 7],
  ["Angola", -12, 18, 6],
  ["Zambia", -13, 28, 5],
  ["Botswana", -22, 24, 4],
  ["Namibia", -22, 17, 5],
  ["Australia", -25, 134, 15],
  ["New Zealand", -41, 174, 5],
  ["Indonesia", -2, 118, 10],
  ["Philippines", 13, 122, 5],
  ["Thailand", 15, 101, 5],
  ["Vietnam", 16, 108, 4],
  ["Myanmar", 19, 96, 5],
  ["Malaysia", 4, 109, 5],
  ["USA", 39, -98, 15],
  ["Mexico", 23, -102, 8],
  ["Guatemala", 15, -90, 3],
  ["Colombia", 4, -72, 6],
  ["Venezuela", 8, -66, 5],
  ["Brazil", -10, -52, 15],
  ["Peru", -10, -76, 7],
  ["Argentina", -35, -64, 10],
  ["Chile", -33, -71, 8],
  ["Arctic", 78, 0, 15],
  ["Antarctica", -78, 0, 15],
];

export function reverseGeocode(lat: number, lng: number): string | null {
  let bestName: string | null = null;
  let bestDist = Infinity;

  for (const [name, cLat, cLng, radius] of REGION_CENTROIDS) {
    const dist = Math.sqrt((lat - cLat) ** 2 + (lng - cLng) ** 2);
    if (dist < radius && dist < bestDist) {
      bestDist = dist;
      bestName = name;
    }
  }

  return bestName;
}
