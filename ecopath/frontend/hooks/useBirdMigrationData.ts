"use client";

import { useMemo } from "react";
import { aggregateByWeek } from "@/lib/aggregateByWeek";
import type { EBirdObservation } from "@/lib/types";

export interface MigrationTrafficPoint {
  key: string;
  position: [number, number];
  weight: number;
  count: number;
  active: boolean;
}

export interface MovementArrowPoint {
  key: string;
  position: [number, number];
  bearing: number;
  intensity: number;
}

export interface StationPoint {
  key: string;
  position: [number, number];
  active: boolean;
}

export interface MigrationFrame {
  week: number;
  date: Date;
  label: string;
  points: MigrationTrafficPoint[];
  totalCount: number;
}

interface UseBirdMigrationDataOptions {
  observations?: EBirdObservation[];
  currentWeek: number;
}

const CELL_SIZE_DEGREES = 2;
const TOTAL_FRAMES = 52;

export function useBirdMigrationData({
  observations,
  currentWeek,
}: UseBirdMigrationDataOptions) {
  return useMemo(() => {
    const validObservations = (observations ?? []).filter(isValidObservation);
    const weeklyMap = aggregateByWeek(validObservations);
    const rawFrames = Array.from({ length: TOTAL_FRAMES }, (_, index) =>
      buildFrame(index + 1, weeklyMap.get(index + 1) ?? [])
    );

    const maxPointCount = Math.max(
      1,
      ...rawFrames.flatMap((frame) => frame.points.map((point) => point.count))
    );

    const frames = rawFrames.map((frame) => ({
      ...frame,
      points: frame.points.map((point) => ({
        ...point,
        weight: point.count / maxPointCount,
      })),
    }));

    const frameIndex = Math.min(Math.max(currentWeek - 1, 0), TOTAL_FRAMES - 1);
    const currentFrame = frames[frameIndex] ?? frames[0];
    const nextFrame = findNextFrameWithPoints(frames, frameIndex);
    const currentFramePoints = currentFrame?.points ?? [];
    
    let arrowPoints = buildArrowPoints(currentFramePoints, nextFrame?.points ?? []);
    if (arrowPoints.length === 0 && frameIndex > 0) {
      const prevFrame = frames[frameIndex - 1];
      if (prevFrame && prevFrame.points.length > 0) {
        const prevArrows = buildArrowPoints(prevFrame.points, currentFramePoints);
        arrowPoints = prevArrows
          .map((a) => {
            const ptN = currentFramePoints.find((p) => p.key === a.key);
            if (!ptN) return null;
            return {
              ...a,
              position: ptN.position,
              intensity: Math.max(0, Math.min(1, ptN.weight)),
            } as MovementArrowPoint;
          })
          .filter((a): a is MovementArrowPoint => a !== null);
      }
    }

    const stationPoints = buildStationPoints(frames, currentFramePoints);
    const maxFrameTotal = Math.max(1, ...frames.map((frame) => frame.totalCount));
    const birdsInFlight = (currentFrame.totalCount / maxFrameTotal) * 50;
    const nextBirdsInFlight = ((nextFrame?.totalCount ?? 0) / maxFrameTotal) * 50;

    return {
      frames,
      currentFrame,
      currentFramePoints,
      nextFramePoints: nextFrame?.points ?? [],
      arrowPoints,
      stationPoints,
      birdsInFlight,
      nextBirdsInFlight,
      availableDates: frames.map((frame) => ({
        week: frame.week,
        label: frame.label,
        date: frame.date,
      })),
      migrationBounds: computeMigrationBounds(validObservations, weeklyMap),
    };
  }, [currentWeek, observations]);
}

function isValidObservation(obs: EBirdObservation) {
  return (
    Number.isFinite(obs.lat) &&
    Number.isFinite(obs.lng) &&
    obs.lat >= -90 &&
    obs.lat <= 90 &&
    obs.lng >= -180 &&
    obs.lng <= 180 &&
    !(obs.lat === 0 && obs.lng === 0)
  );
}

function buildFrame(week: number, observations: EBirdObservation[]): MigrationFrame {
  const cells = new Map<
    string,
    { lngSum: number; latSum: number; count: number; observations: EBirdObservation[] }
  >();

  for (const obs of observations) {
    const count = Math.max(0, obs.count || 1);
    const lngCell = Math.round(obs.lng / CELL_SIZE_DEGREES);
    const latCell = Math.round(obs.lat / CELL_SIZE_DEGREES);
    const key = `${lngCell}:${latCell}`;
    const cell = cells.get(key) ?? {
      lngSum: 0,
      latSum: 0,
      count: 0,
      observations: [],
    };

    cell.lngSum += obs.lng * count;
    cell.latSum += obs.lat * count;
    cell.count += count;
    cell.observations.push(obs);
    cells.set(key, cell);
  }

  const points = Array.from(cells.entries()).map(([key, cell]) => ({
    key,
    position: [
      cell.count > 0 ? cell.lngSum / cell.count : 0,
      cell.count > 0 ? cell.latSum / cell.count : 0,
    ] as [number, number],
    weight: 0,
    count: cell.count,
    active: cell.count > 0,
  }));

  const totalCount = points.reduce((sum, point) => sum + point.count, 0);
  const frameDate = pickFrameDate(week, observations);

  return {
    week,
    date: frameDate,
    label: formatFrameLabel(frameDate, week),
    points,
    totalCount,
  };
}

function pickFrameDate(week: number, observations: EBirdObservation[]) {
  const dated = observations
    .map((obs) => new Date(obs.date))
    .filter((date) => !Number.isNaN(date.getTime()))
    .sort((a, b) => b.getTime() - a.getTime());

  if (dated[0]) return dated[0];

  const year = new Date().getFullYear();
  const jan1 = new Date(year, 0, 1, 12);
  return new Date(jan1.getTime() + (week - 1) * 7 * 86400000);
}

function formatFrameLabel(date: Date, week: number) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}/${mm}/${dd} · W${String(week).padStart(2, "0")}`;
}

function findNextFrameWithPoints(frames: MigrationFrame[], frameIndex: number) {
  for (let offset = 1; offset < frames.length; offset++) {
    const next = frames[(frameIndex + offset) % frames.length];
    if (next.points.length > 0) return next;
  }

  return null;
}

function buildArrowPoints(
  currentPoints: MigrationTrafficPoint[],
  nextPoints: MigrationTrafficPoint[]
): MovementArrowPoint[] {
  const cellsCurrent = new Map(currentPoints.map(p => [p.key, p]));
  const cellsNext = new Map(nextPoints.map(p => [p.key, p]));
  const arrows: MovementArrowPoint[] = [];

  for (const [key, cellN] of cellsCurrent.entries()) {
    const cellNp1 = cellsNext.get(key);
    if (!cellNp1) continue;

    const dlng = cellNp1.position[0] - cellN.position[0];
    const dlat = cellNp1.position[1] - cellN.position[1];
    
    // Using a distance threshold based on roughly 0.3 degrees to filter noise
    const dist = Math.sqrt(dlat * dlat + dlng * dlng);
    if (dist < 0.3) continue;

    const bearing = (Math.atan2(dlng, dlat) * 180) / Math.PI;

    arrows.push({
      key,
      position: cellN.position,
      bearing,
      intensity: Math.max(0, Math.min(1, cellN.weight)),
    });
  }

  // Optionally cap arrows around top 80 most significant ones or return all
  return arrows.sort((a, b) => b.intensity - a.intensity).slice(0, 80);
}

export function getInterpolatedFrame(
  frameN: MigrationTrafficPoint[],     
  frameNplus1: MigrationTrafficPoint[], 
  progress: number                     
): MigrationTrafficPoint[] {          
  const cells = new Map<string, MigrationTrafficPoint>();

  for (const pt of frameN) {
    cells.set(pt.key, { ...pt, weight: pt.weight * (1 - progress), count: Math.round(pt.count * (1 - progress)) });
  }

  for (const pt of frameNplus1) {
    const existing = cells.get(pt.key);
    if (existing) {
      existing.weight += pt.weight * progress;
      existing.count += Math.round(pt.count * progress);
    } else {
      cells.set(pt.key, { ...pt, weight: pt.weight * progress, count: Math.round(pt.count * progress) });
    }
  }

  return Array.from(cells.values()).filter(d => d.weight > 0.01);
}

function buildStationPoints(
  frames: MigrationFrame[],
  currentPoints: MigrationTrafficPoint[]
): StationPoint[] {
  const activeKeys = new Set(currentPoints.map((point) => point.key));
  const stations = new Map<string, { lngSum: number; latSum: number; count: number }>();

  for (const frame of frames) {
    for (const point of frame.points) {
      const station = stations.get(point.key) ?? { lngSum: 0, latSum: 0, count: 0 };
      station.lngSum += point.position[0];
      station.latSum += point.position[1];
      station.count += 1;
      stations.set(point.key, station);
    }
  }

  return Array.from(stations.entries()).map(([key, station]) => ({
    key,
    position: [
      station.lngSum / station.count,
      station.latSum / station.count,
    ] as [number, number],
    active: activeKeys.has(key),
  }));
}

function computeMigrationBounds(
  observations: EBirdObservation[],
  weeklyMap: Map<number, EBirdObservation[]>
): [number, number, number, number] | null {
  const breeding = collectWeeks(weeklyMap, 20, 32);
  const wintering = [
    ...collectWeeks(weeklyMap, 44, 52),
    ...collectWeeks(weeklyMap, 1, 8),
  ];
  const seasonal = [...breeding, ...wintering];
  const source = seasonal.length >= 2 ? seasonal : observations;
  if (source.length < 2) return null;

  let minLng = 180;
  let maxLng = -180;
  let minLat = 90;
  let maxLat = -90;

  for (const obs of source) {
    minLng = Math.min(minLng, obs.lng);
    maxLng = Math.max(maxLng, obs.lng);
    minLat = Math.min(minLat, obs.lat);
    maxLat = Math.max(maxLat, obs.lat);
  }

  if (!Number.isFinite(minLng) || !Number.isFinite(minLat)) return null;

  const lngPad = Math.max((maxLng - minLng) * 0.1, 2);
  const latPad = Math.max((maxLat - minLat) * 0.1, 2);

  return [
    Math.max(-180, minLng - lngPad),
    Math.max(-85, minLat - latPad),
    Math.min(180, maxLng + lngPad),
    Math.min(85, maxLat + latPad),
  ];
}

function collectWeeks(
  weeklyMap: Map<number, EBirdObservation[]>,
  start: number,
  end: number
) {
  const result: EBirdObservation[] = [];
  for (let week = start; week <= end; week++) {
    result.push(...(weeklyMap.get(week) ?? []));
  }
  return result;
}
