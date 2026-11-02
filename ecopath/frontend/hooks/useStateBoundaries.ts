'use client';

import { useEffect, useState } from 'react';
import type { FeatureCollection } from 'geojson';
import { BOUNDARY_URL } from '../components/chat/blocks/map-config';

type Status = 'loading' | 'ready' | 'error';

// Module-level cache: the boundary file is ~80KB and every map block in a
// conversation wants the same one, so it is fetched at most once per session.
let cached: FeatureCollection | null = null;
let inFlight: Promise<FeatureCollection> | null = null;

export function getStateBoundaries(): Promise<FeatureCollection> {
  if (cached) return Promise.resolve(cached);
  if (!inFlight) {
    inFlight = fetch(BOUNDARY_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`Boundary fetch failed: ${res.status}`);
        return res.json();
      })
      .then((data: FeatureCollection) => {
        if (!data || data.type !== 'FeatureCollection' || !Array.isArray(data.features)) {
          throw new Error('Boundary data is not a FeatureCollection');
        }
        cached = data;
        return data;
      })
      .catch((err) => {
        // Let a later map retry rather than caching the failure forever.
        inFlight = null;
        throw err;
      });
  }
  return inFlight;
}

/**
 * Indian state boundaries for the chat maps.
 *
 * Resolves to `error` rather than throwing: a map that can't colour its regions
 * should still show its base tiles, not blow up the whole message.
 */
export function useStateBoundaries(enabled = true) {
  const [data, setData] = useState<FeatureCollection | null>(cached);
  const [status, setStatus] = useState<Status>(cached ? 'ready' : 'loading');

  useEffect(() => {
    if (!enabled || cached) return;
    let active = true;

    getStateBoundaries().then(
      (fc) => {
        if (!active) return;
        setData(fc);
        setStatus('ready');
      },
      () => {
        if (!active) return;
        setStatus('error');
      },
    );

    return () => {
      active = false;
    };
  }, [enabled]);

  return { boundaries: data, status };
}
