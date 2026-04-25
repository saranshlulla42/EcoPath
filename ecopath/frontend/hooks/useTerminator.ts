"use client";

import { useMemo } from "react";

export function getTerminatorCoords(date: Date): [number, number][] {
  const start = new Date(date.getFullYear(), 0, 0);
  const dayOfYear = Math.floor((date.getTime() - start.getTime()) / 86400000);

  const radians = (deg: number) => (deg * Math.PI) / 180;
  const degrees = (rad: number) => (rad * 180) / Math.PI;

  const decl =
    23.45 * Math.sin(radians((360 / 365) * (dayOfYear - 81)));

  const utcHours =
    date.getUTCHours() +
    date.getUTCMinutes() / 60 +
    date.getUTCSeconds() / 3600;

  const sunHourAngle = (utcHours - 12) * 15;
  const coords: [number, number][] = [];

  for (let lng = -180; lng <= 180; lng += 2) {
    const lat = degrees(
      Math.atan(
        -Math.cos(radians(lng - sunHourAngle)) /
          Math.tan(radians(decl))
      )
    );

    if (Number.isFinite(lat)) {
      coords.push([lng, Math.max(-85, Math.min(85, lat))]);
    }
  }

  return coords;
}

export function useTerminator(date: Date | string | null | undefined) {
  return useMemo(() => {
    const parsed = date ? new Date(date) : new Date();
    return getTerminatorCoords(
      Number.isNaN(parsed.getTime()) ? new Date() : parsed
    );
  }, [date]);
}
