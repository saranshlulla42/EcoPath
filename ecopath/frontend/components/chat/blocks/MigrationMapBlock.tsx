'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Layer, Marker, Source, type MapRef } from 'react-map-gl/maplibre';
import type { FeatureCollection } from 'geojson';
import 'maplibre-gl/dist/maplibre-gl.css';

import type {
  MigrationMapBlock as MigrationMapBlockType,
  MigrationRoute,
  MigrationStopover,
} from '../../../types/chat';
import { MapBlockFrame, useTouchGuard, type MapFrameContext } from './MapBlockFrame';
import { MAP_INTERACTION, MAP_STYLE, MULTI_ROUTE_COLORS, ROUTE_COLORS } from './map-config';

const DASH_LAYER_ID = 'route-dash';
const BASE_LAYER_ID = 'route-base';
const GLOW_LAYER_ID = 'route-glow';
const FIT_PADDING = { top: 36, bottom: 36, left: 36, right: 36 };
const FALLBACK_VIEW = { longitude: 85, latitude: 25, zoom: 3 };

/**
 * Successive dash patterns. Cycling through them shifts the gaps along the line,
 * which reads as flow in the direction of travel — MapLibre won't animate
 * `line-dasharray` on its own.
 */
const DASH_SEQUENCE: [number, number, ...number[]][] = [
  [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5],
  [3, 4, 0], [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2],
  [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5],
];

/** ~30fps is plenty for a dash cycle and halves the work of a 60fps loop. */
const FRAME_INTERVAL_MS = 33;

const isFiniteCoord = (c: unknown): c is [number, number] =>
  Array.isArray(c) && c.length >= 2 && Number.isFinite(c[0]) && Number.isFinite(c[1]);

/** Drops malformed points and routes too short to form a line. */
function usableRoutes(routes: MigrationRoute[] | undefined) {
  return (routes ?? [])
    .map((route, index) => ({
      ...route,
      color: route.color || MULTI_ROUTE_COLORS[index % MULTI_ROUTE_COLORS.length],
      coordinates: (route.coordinates ?? []).filter(isFiniteCoord).map(
        (c) => [c[0], c[1]] as [number, number],
      ),
    }))
    .filter((route) => route.coordinates.length >= 2);
}

function buildRouteGeoJSON(routes: ReturnType<typeof usableRoutes>): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: routes.map((route, index) => ({
      type: 'Feature',
      properties: {
        name: route.name ?? '',
        color: route.color ?? ROUTE_COLORS.default,
        index,
      },
      geometry: { type: 'LineString', coordinates: route.coordinates },
    })),
  };
}

function StopoverMarker({ stopover, delay }: { stopover: MigrationStopover; delay: number }) {
  const [showTooltip, setShowTooltip] = useState(false);
  const { markTouch, isEmulatedMouse } = useTouchGuard();

  return (
    <Marker longitude={stopover.lng} latitude={stopover.lat} anchor="center">
      <div className="stopover-enter" style={{ animationDelay: `${delay}ms` }}>
        <div
          className="stopover-marker"
          onTouchStart={markTouch}
          // Hover on a pointer device; tap toggles. The guard keeps the mouse
          // events synthesised after a tap from cancelling the tap itself.
          onMouseEnter={() => { if (!isEmulatedMouse()) setShowTooltip(true); }}
          onMouseLeave={() => { if (!isEmulatedMouse()) setShowTooltip(false); }}
          onClick={() => setShowTooltip((v) => !v)}
        >
          <span className="stopover-ping" />
          <span className="stopover-dot" />
          {showTooltip && (
            <div className="stopover-tooltip">
              <strong>{stopover.name}</strong>
              {stopover.notes && <p>{stopover.notes}</p>}
            </div>
          )}
          <span className="stopover-label">{stopover.name}</span>
        </div>
      </div>
    </Marker>
  );
}

function MigrationMap({ block, ctx }: { block: MigrationMapBlockType; ctx: MapFrameContext }) {
  const mapRef = useRef<MapRef>(null);
  const frameRef = useRef<number | null>(null);
  const stepRef = useRef(0);
  const lastFrameRef = useRef(0);

  const routes = useMemo(() => usableRoutes(block.routes), [block.routes]);
  const stopovers = useMemo(
    () => (block.stopovers ?? []).filter((s) => Number.isFinite(s?.lng) && Number.isFinite(s?.lat)),
    [block.stopovers],
  );
  const routeData = useMemo(() => buildRouteGeoJSON(routes), [routes]);

  const bounds = useMemo(() => {
    let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
    let seen = false;
    const extend = (lng: number, lat: number) => {
      seen = true;
      minLng = Math.min(minLng, lng); minLat = Math.min(minLat, lat);
      maxLng = Math.max(maxLng, lng); maxLat = Math.max(maxLat, lat);
    };
    routes.forEach((r) => r.coordinates.forEach(([lng, lat]) => extend(lng, lat)));
    stopovers.forEach((s) => extend(s.lng, s.lat));
    return seen ? ([[minLng, minLat], [maxLng, maxLat]] as [[number, number], [number, number]]) : null;
  }, [routes, stopovers]);

  const initialView = block.center
    ? { longitude: block.center[0], latitude: block.center[1], zoom: block.zoom ?? 3.5 }
    : FALLBACK_VIEW;

  const stopAnimation = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }, []);

  const startAnimation = useCallback(() => {
    if (frameRef.current !== null) return;

    const tick = (now: number) => {
      const map = mapRef.current?.getMap();
      if (!map || !map.getLayer(DASH_LAYER_ID)) {
        frameRef.current = null;
        return;
      }
      if (now - lastFrameRef.current >= FRAME_INTERVAL_MS) {
        lastFrameRef.current = now;
        stepRef.current = (stepRef.current + 1) % DASH_SEQUENCE.length;
        map.setPaintProperty(DASH_LAYER_ID, 'line-dasharray', DASH_SEQUENCE[stepRef.current]);
      }
      frameRef.current = requestAnimationFrame(tick);
    };

    frameRef.current = requestAnimationFrame(tick);
  }, []);

  // Second stage of the reveal: the route fades up over the dark tiles while the
  // dashes are already flowing, so the line reads as being laid down.
  const handleLoad = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (bounds) {
      mapRef.current?.fitBounds(bounds, { padding: FIT_PADDING, maxZoom: 8, duration: 0 });
    }
    if (map) {
      [GLOW_LAYER_ID, BASE_LAYER_ID, DASH_LAYER_ID].forEach((id, i) => {
        if (!map.getLayer(id)) return;
        const target = [0.35, 0.6, 0.95][i];
        map.setPaintProperty(id, 'line-opacity-transition', { duration: 800, delay: 0 });
        map.setPaintProperty(id, 'line-opacity', target);
      });
    }
    startAnimation();
  }, [bounds, startAnimation]);

  // Off-screen maps keep their WebGL context but stop burning frames on an
  // animation nobody is looking at.
  useEffect(() => {
    if (ctx.isInViewport) startAnimation();
    else stopAnimation();
  }, [ctx.isInViewport, startAnimation, stopAnimation]);

  useEffect(() => stopAnimation, [stopAnimation]);

  return (
    <Map
      ref={mapRef}
      initialViewState={initialView}
      style={{ width: '100%', height: ctx.height }}
      mapStyle={MAP_STYLE}
      attributionControl={false}
      {...MAP_INTERACTION}
      onLoad={handleLoad}
    >
      {routes.length > 0 && (
        <Source id="migration-routes" type="geojson" data={routeData}>
          {/* Soft halo under the line. */}
          <Layer
            id={GLOW_LAYER_ID}
            type="line"
            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{
              'line-color': ['get', 'color'] as never,
              'line-width': 12,
              'line-blur': 8,
              'line-opacity': 0,
            }}
          />
          {/* The full path. */}
          <Layer
            id={BASE_LAYER_ID}
            type="line"
            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{
              'line-color': ['get', 'color'] as never,
              'line-width': 2.5,
              'line-opacity': 0,
            }}
          />
          {/* The flowing dashes on top. */}
          <Layer
            id={DASH_LAYER_ID}
            type="line"
            layout={{ 'line-cap': 'butt', 'line-join': 'round' }}
            paint={{
              'line-color': ['get', 'color'] as never,
              'line-width': 2.5,
              'line-dasharray': DASH_SEQUENCE[0] as never,
              'line-opacity': 0,
            }}
          />
        </Source>
      )}

      {stopovers.map((stopover, index) => (
        <StopoverMarker
          key={`${stopover.name}-${stopover.lng}-${stopover.lat}`}
          stopover={stopover}
          // Stagger by position along the route, so the stops light up in order.
          delay={200 + ((stopover.order ?? index + 1) - 1) * 140}
        />
      ))}
    </Map>
  );
}

export function MigrationMapBlockView({ block }: { block: MigrationMapBlockType }) {
  const title = block.title || (block.species ? `${block.species} Migration` : undefined);
  return (
    <MapBlockFrame title={title}>
      {(ctx) => <MigrationMap block={block} ctx={ctx} />}
    </MapBlockFrame>
  );
}
