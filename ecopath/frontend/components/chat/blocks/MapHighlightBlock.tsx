'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import Map, { Layer, Marker, Source, type MapLayerMouseEvent, type MapRef } from 'react-map-gl/maplibre';
import type { FeatureCollection } from 'geojson';
import 'maplibre-gl/dist/maplibre-gl.css';

import type { MapHighlightBlock as MapHighlightBlockType, MapHighlightRegion } from '../../../types/chat';
import { useStateBoundaries } from '../../../hooks/useStateBoundaries';
import { getRegionCentroid, normalizeRegionCode } from './region-labels';
import { MapBlockFrame, MapNotice, useTouchGuard, type MapFrameContext } from './MapBlockFrame';
import {
  COMPARISON_COLORS,
  GRADIENT_COLORS,
  GradientKind,
  HIGHLIGHT_FILL_OPACITY,
  MAP_INTERACTION,
  MAP_STYLE,
  REGION_CODE_PROPERTY,
  getOutlineColor,
  interpolateColor,
} from './map-config';

const FILL_LAYER_ID = 'highlighted-regions-fill';
const FIT_PADDING = { top: 32, bottom: 32, left: 32, right: 32 };
const INDIA_VIEW = { longitude: 78.96, latitude: 22.5, zoom: 3.8 };

type Bounds = [[number, number], [number, number]];

/** Colour for a single region, resolved in JS since MapLibre can't ramp per-feature. */
function regionColor(region: MapHighlightRegion, gradient: GradientKind, index: number): string {
  if (gradient === 'comparison') {
    return COMPARISON_COLORS[index % COMPARISON_COLORS.length].fill;
  }
  const ramp = GRADIENT_COLORS[gradient as 'decline'] ?? GRADIENT_COLORS.neutral;
  const intensity = typeof region.intensity === 'number' ? region.intensity : 0.6;
  return interpolateColor(ramp.low, ramp.high, intensity);
}

/** `['in', code, [...codes]]` — restricts a layer to the highlighted regions. */
function buildHighlightFilter(codes: string[]): unknown[] {
  return ['in', ['get', REGION_CODE_PROPERTY], ['literal', codes]];
}

const TRANSPARENT = 'rgba(0,0,0,0)';

/**
 * `['case', ['==', code, 'GJ'], '<colour>', …, transparent]`.
 *
 * With no regions this returns the flat fallback rather than a bare
 * `['case', fallback]` — MapLibre rejects a `case` with fewer than 3 arguments.
 */
function buildColorExpression(
  regions: MapHighlightRegion[],
  gradient: GradientKind,
  pick: (region: MapHighlightRegion, index: number) => string,
): unknown[] | string {
  if (regions.length === 0) return TRANSPARENT;

  const cases: unknown[] = ['case'];
  regions.forEach((region, index) => {
    cases.push(['==', ['get', REGION_CODE_PROPERTY], normalizeRegionCode(region.code)]);
    cases.push(pick(region, index));
  });
  cases.push(TRANSPARENT);
  return cases;
}

/** Bounding box of the highlighted features, falling back to their label points. */
function computeBounds(
  boundaries: FeatureCollection | null,
  regions: MapHighlightRegion[],
): Bounds | null {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  let seen = false;

  const extend = (lng: number, lat: number) => {
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
    seen = true;
    if (lng < minLng) minLng = lng;
    if (lat < minLat) minLat = lat;
    if (lng > maxLng) maxLng = lng;
    if (lat > maxLat) maxLat = lat;
  };

  // Walk the nested coordinate arrays of Polygon / MultiPolygon geometries.
  const walk = (coords: unknown) => {
    if (!Array.isArray(coords)) return;
    if (typeof coords[0] === 'number' && typeof coords[1] === 'number') {
      extend(coords[0] as number, coords[1] as number);
      return;
    }
    coords.forEach(walk);
  };

  const wanted = new Set(regions.map((r) => normalizeRegionCode(r.code)));

  if (boundaries) {
    for (const feature of boundaries.features) {
      const code = feature.properties?.[REGION_CODE_PROPERTY];
      if (typeof code === 'string' && wanted.has(code) && feature.geometry) {
        walk((feature.geometry as { coordinates?: unknown }).coordinates);
      }
    }
  }

  // Codes with no matching feature still contribute their label point, so a
  // stale or unknown code doesn't silently drop out of the framing.
  if (!seen) {
    regions.forEach((region) => {
      const centroid = getRegionCentroid(region.code);
      if (centroid) extend(centroid[0], centroid[1]);
    });
  }

  return seen ? [[minLng, minLat], [maxLng, maxLat]] : null;
}

function RegionLabel({ region, hidden }: { region: MapHighlightRegion; hidden: boolean }) {
  const centroid = getRegionCentroid(region.code);
  if (!centroid) return null;

  // Kept mounted and merely hidden — markers are re-measured on every pan, and
  // unmounting them would churn the DOM throughout the gesture.
  //
  // pointer-events:none on the marker itself matters: the label sits on the
  // region's centre, which is exactly where someone points to inspect it. Left
  // interactive, it would swallow the hover meant for the fill underneath.
  return (
    <Marker
      longitude={centroid[0]}
      latitude={centroid[1]}
      anchor="center"
      style={{ pointerEvents: 'none' }}
    >
      <div className="region-label" style={{ visibility: hidden ? 'hidden' : 'visible' }}>
        <span className="region-label-name">{region.name || normalizeRegionCode(region.code)}</span>
        {region.label && <span className="region-label-value">{region.label}</span>}
      </div>
    </Marker>
  );
}

/**
 * Rough on-screen size of a label, in px — cheaper than measuring the DOM, and
 * close enough to decide overlap: an 11px semibold name over a 10px value line.
 * The per-character figures run slightly wide, and GUTTER is added on top, so
 * neighbouring labels end up with visible air between them rather than merely
 * not touching.
 */
const GUTTER = { x: 14, y: 8 };

function labelBox(region: MapHighlightRegion, x: number, y: number) {
  const nameWidth = (region.name?.length ?? 2) * 7.0;
  const valueWidth = (region.label?.length ?? 0) * 6.0;
  const width = Math.max(nameWidth, valueWidth) + GUTTER.x;
  const height = (region.label ? 30 : 17) + GUTTER.y;
  return { x1: x - width / 2, x2: x + width / 2, y1: y - height / 2, y2: y + height / 2 };
}

const overlaps = (a: ReturnType<typeof labelBox>, b: ReturnType<typeof labelBox>) =>
  a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;

function HighlightMap({
  block,
  ctx,
}: {
  block: MapHighlightBlockType;
  ctx: MapFrameContext;
}) {
  const mapRef = useRef<MapRef>(null);
  const [hovered, setHovered] = useState<MapHighlightRegion | null>(null);
  const [tooltipAt, setTooltipAt] = useState({ x: 0, y: 0 });

  // null until the first measurement, when every label is shown.
  const [visibleLabels, setVisibleLabels] = useState<Set<string> | null>(null);

  const { markTouch, isEmulatedMouse } = useTouchGuard();

  const { boundaries, status } = useStateBoundaries();
  const gradient: GradientKind = block.gradient ?? 'neutral';
  const regions = useMemo(() => block.regions ?? [], [block.regions]);

  const codes = useMemo(
    () => regions.map((r) => normalizeRegionCode(r.code)).filter(Boolean),
    [regions],
  );

  const fillColor = useMemo(
    () => buildColorExpression(regions, gradient, (r, i) => regionColor(r, gradient, i)),
    [regions, gradient],
  );

  const outlineColor = useMemo(
    () =>
      gradient === 'comparison'
        ? buildColorExpression(
            regions,
            gradient,
            (_r, i) => COMPARISON_COLORS[i % COMPARISON_COLORS.length].outline,
          )
        : getOutlineColor(gradient),
    [regions, gradient],
  );

  const filter = useMemo(() => buildHighlightFilter(codes), [codes]);
  const bounds = useMemo(() => computeBounds(boundaries, regions), [boundaries, regions]);

  const initialView = block.center
    ? { longitude: block.center[0], latitude: block.center[1], zoom: block.zoom ?? 5 }
    : INDIA_VIEW;

  /**
   * Hide labels that would collide.
   *
   * Several small neighbouring states (Kerala next to Tamil Nadu, or the
   * north-east cluster) put their labels on top of each other once the map is
   * zoomed out far enough to hold them all. Strongest highlight wins the space;
   * the ones it covers drop out rather than overprinting.
   */
  const recomputeLabels = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;

    const byPriority = [...regions].sort(
      (a, b) => (b.intensity ?? 0) - (a.intensity ?? 0) || (b.value ?? 0) - (a.value ?? 0),
    );

    const placed: ReturnType<typeof labelBox>[] = [];
    const visible = new Set<string>();

    for (const region of byPriority) {
      const centroid = getRegionCentroid(region.code);
      if (!centroid) continue;
      const point = map.project(centroid);
      const box = labelBox(region, point.x, point.y);
      if (placed.some((other) => overlaps(box, other))) continue;
      placed.push(box);
      visible.add(normalizeRegionCode(region.code));
    }

    // Only re-render when the visible set actually changed — this runs on every
    // frame of a pan.
    setVisibleLabels((prev) => {
      if (prev && prev.size === visible.size && [...visible].every((c) => prev.has(c))) {
        return prev;
      }
      return visible;
    });
  }, [regions]);

  // Second stage of the reveal: the container has already slid in and the dark
  // tiles have painted, so fade the colour on top of them.
  const revealFills = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map || !map.getLayer(FILL_LAYER_ID)) return;
    map.setPaintProperty(FILL_LAYER_ID, 'fill-opacity-transition', { duration: 600, delay: 0 });
    map.setPaintProperty(FILL_LAYER_ID, 'fill-opacity', HIGHLIGHT_FILL_OPACITY);
  }, []);

  const handleLoad = useCallback(() => {
    if (bounds) {
      // Instant, not animated — the map has only just appeared, so a fly-in
      // would read as the map correcting itself in front of the user.
      mapRef.current?.fitBounds(bounds, { padding: FIT_PADDING, maxZoom: 7, duration: 0 });
    }
    revealFills();
    recomputeLabels();
  }, [bounds, revealFills, recomputeLabels]);

  const handleMouseMove = useCallback(
    (event: MapLayerMouseEvent) => {
      // Ignore the mouse events MapLibre synthesises right after a tap.
      if (isEmulatedMouse()) return;

      const code = event.features?.[0]?.properties?.[REGION_CODE_PROPERTY];
      const region = code
        ? regions.find((r) => normalizeRegionCode(r.code) === code)
        : undefined;

      if (region) {
        setHovered(region);
        setTooltipAt({ x: event.point.x, y: event.point.y });
      } else {
        setHovered(null);
      }
    },
    [regions, isEmulatedMouse],
  );

  // Touch devices get no hover, so a tap toggles the same tooltip.
  const handleClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const code = event.features?.[0]?.properties?.[REGION_CODE_PROPERTY];
      const region = code
        ? regions.find((r) => normalizeRegionCode(r.code) === code)
        : undefined;

      if (!region) {
        setHovered(null);
        return;
      }
      setTooltipAt({ x: event.point.x, y: event.point.y });
      setHovered((prev) => (prev?.code === region.code ? null : region));
    },
    [regions],
  );

  const hasBoundaries = status === 'ready' && !!boundaries;

  return (
    <>
      <Map
        ref={mapRef}
        initialViewState={initialView}
        style={{ width: '100%', height: ctx.height }}
        mapStyle={MAP_STYLE}
        attributionControl={false}
        {...MAP_INTERACTION}
        interactiveLayerIds={hasBoundaries && codes.length ? [FILL_LAYER_ID] : []}
        onLoad={handleLoad}
        onMove={recomputeLabels}
        onResize={recomputeLabels}
        onTouchStart={markTouch}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => { if (!isEmulatedMouse()) setHovered(null); }}
        onClick={handleClick}
      >
        {hasBoundaries && (
          <Source id="state-boundaries" type="geojson" data={boundaries}>
            {/* Context: every region, barely there, so the highlights carry the eye. */}
            <Layer
              id="all-regions-fill"
              type="fill"
              paint={{
                'fill-color': 'rgba(255, 255, 255, 0.02)',
                'fill-outline-color': 'rgba(255, 255, 255, 0.08)',
              }}
            />
            {/* Nothing to highlight — render the context fill only. */}
            {codes.length > 0 && (
              <Layer
                id={FILL_LAYER_ID}
                type="fill"
                filter={filter as never}
                paint={{
                  'fill-color': fillColor as never,
                  'fill-opacity': 0,
                }}
              />
            )}
            {codes.length > 0 && (
              <Layer
                id="highlighted-regions-outline"
                type="line"
                filter={filter as never}
                paint={{
                  'line-color': outlineColor as never,
                  'line-width': 1.5,
                  'line-opacity': 0.8,
                }}
              />
            )}
          </Source>
        )}

        {regions.map((region) => (
          <RegionLabel
            key={`${region.code}-${region.name}`}
            region={region}
            hidden={!!visibleLabels && !visibleLabels.has(normalizeRegionCode(region.code))}
          />
        ))}
      </Map>

      {hovered && (
        <div
          className="map-tooltip"
          style={{ left: tooltipAt.x + 12, top: tooltipAt.y - 12 }}
        >
          <strong>{hovered.name || normalizeRegionCode(hovered.code)}</strong>
          {hovered.label && <span>{hovered.label}</span>}
          {!hovered.label && typeof hovered.value === 'number' && (
            <span>{hovered.value.toLocaleString()}</span>
          )}
        </div>
      )}

      {status === 'error' && <MapNotice>Boundary data unavailable</MapNotice>}
    </>
  );
}

export function MapHighlightBlockView({ block }: { block: MapHighlightBlockType }) {
  return (
    <MapBlockFrame title={block.title} narrative={block.narrative}>
      {(ctx) => <HighlightMap block={block} ctx={ctx} />}
    </MapBlockFrame>
  );
}
