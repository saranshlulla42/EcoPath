"use client";

import { useMemo, useState, useEffect, useCallback, useRef } from "react";
import Map, { Marker, NavigationControl } from "react-map-gl/maplibre";
import type { MapRef } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import DeckGL from "@deck.gl/react";
import type { Layer, MapViewState, ViewStateChangeParameters } from "@deck.gl/core";
import { IconLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { PathStyleExtension } from "@deck.gl/extensions";
import { TripsLayer } from "@deck.gl/geo-layers";
import type { MovebankTrack } from "@/lib/types";
import { BirdsInFlightCounter } from "./BirdsInFlightCounter";
import { MigrationLegend } from "./MigrationLegend";
import {
  pointAlongLine,
  reverseGeocode,
} from "@/lib/migrationUtils";

const MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const DEFAULT_VIEW_STATE: MapViewState = {
  longitude: 10,
  latitude: 20,
  zoom: 2,
  pitch: 0,
  bearing: 0,
};

export interface ArcDatum {
  sourcePosition: [number, number]; // [lng, lat]
  targetPosition: [number, number];
  color: [number, number, number, number];
  width: number;
}

export interface HeatmapDatum {
  position: [number, number]; // [lng, lat]
  coordinates?: [number, number];
  weight: number;
  count?: number;
  key?: string;
}

export interface MovementArrowDatum {
  key: string;
  position: [number, number];
  bearing: number;
  intensity: number;
}

export interface StationDatum {
  key: string;
  position: [number, number];
  active: boolean;
}

export interface MarkerData {
  origin: { lat: number; lng: number } | null;
  destination: { lat: number; lng: number } | null;
}

export interface ChevronData {
  lng: number;
  lat: number;
  bearing: number;
}

interface MapCanvasProps {
  arcData: ArcDatum[];
  heatmapData: HeatmapDatum[];
  tripData: MovebankTrack[];
  viewMode: "arcs" | "density";
  currentTime?: number;
  trailLength?: number;
  flyToBounds?: [number, number, number, number] | null;
  markers?: MarkerData | null;
  arcCoords?: [number, number][] | null;
  chevrons?: ChevronData[];
  arrowPoints?: MovementArrowDatum[];
  stationPoints?: StationDatum[];
  terminatorCoords?: [number, number][];
  birdsInFlight?: number;
  frameLabel?: string;
  currentWeek?: number;
  isPlaying?: boolean;
  speciesColor?: string;
  speciesKey?: string;
  onZoomStart?: () => void;
  onZoomEnd?: () => void;
}

export function MapCanvas({
  arcData,
  heatmapData,
  tripData,
  viewMode,
  currentTime = 0,
  trailLength = 86400000 * 7,
  flyToBounds,
  markers,
  arcCoords,
  chevrons = [],
  arrowPoints = [],
  stationPoints = [],
  terminatorCoords = [],
  birdsInFlight = 0,
  frameLabel = "",
  currentWeek = 1,
  isPlaying = false,
  speciesColor = "#06b6d4",
  speciesKey = "",
  onZoomStart,
  onZoomEnd,
}: MapCanvasProps) {
  const [viewState, setViewState] = useState<MapViewState>(DEFAULT_VIEW_STATE);
  const userInteractedRef = useRef(false);
  const lastSpeciesKeyRef = useRef("");
  const mapRef = useRef<MapRef>(null);

  function flyToMigrationRegion(
    map: any,
    unionBBox: [number, number, number, number],
    onComplete?: () => void
  ) {
    // Cancel any in-progress camera animation first
    map.stop();

    // Wait one tick to ensure stop() has taken effect
    requestAnimationFrame(() => {
      map.fitBounds(unionBBox, {
        padding: { top: 80, bottom: 120, left: 60, right: 60 },
        duration: 1800,
        easing: (t: number) => t < 0.5 ? 2*t*t : -1+(4-2*t)*t // ease-in-out
      });

      if (onComplete) {
        setTimeout(onComplete, 1900); // fire after animation finishes
      }
    });
  }

  // ── Cinematic sequence state ──────────────────────────────────────────
  // 0 = idle/done, 1 = zooming to origin, 2 = holding at origin,
  // 3 = sweeping to destination, 4 = settling to overview
  const [cinematicPhase, setCinematicPhase] = useState(0);
  const [showOriginMarker, setShowOriginMarker] = useState(false);
  const [showDestMarker, setShowDestMarker] = useState(false);
  const [showChevrons, setShowChevrons] = useState(false);
  const cinematicTimersRef = useRef<NodeJS.Timeout[]>([]);

  const clearCinematic = useCallback(() => {
    for (const t of cinematicTimersRef.current) clearTimeout(t);
    cinematicTimersRef.current = [];
  }, []);

  // Helper to schedule a timeout and track it for cleanup
  const scheduleTimer = useCallback(
    (fn: () => void, ms: number) => {
      const t = setTimeout(fn, ms);
      cinematicTimersRef.current.push(t);
      return t;
    },
    []
  );

  // ── Cinematic fly-through on species change ───────────────────────────
  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !flyToBounds) return;
    if (speciesKey === lastSpeciesKeyRef.current) return;
    lastSpeciesKeyRef.current = speciesKey;
    userInteractedRef.current = false;

    // Reset visual state
    setShowOriginMarker(true);
    setShowDestMarker(true);
    setShowChevrons(true);

    onZoomStart?.();
    flyToMigrationRegion(map, flyToBounds, () => {
      onZoomEnd?.();
    });

  }, [flyToBounds, speciesKey, onZoomStart, onZoomEnd]);

  // ── Handle user interaction — abort cinematic if user pans ────────────
  const handleViewStateChange = useCallback(
    ({ viewState: vs, interactionState }: ViewStateChangeParameters) => {
      if (!isMapViewState(vs)) return;
      setViewState(vs);
      if (
        interactionState?.isPanning ||
        interactionState?.isRotating ||
        interactionState?.isZooming
      ) {
        userInteractedRef.current = true;
        if (cinematicPhase > 0) {
          // User interrupted — abort sequence, show everything immediately
          clearCinematic();
          setCinematicPhase(0);
          setShowOriginMarker(true);
          setShowDestMarker(true);
          setShowChevrons(true);
        }
      }
    },
    [cinematicPhase, clearCinematic]
  );

  // ── Deck.gl layers ────────────────────────────────────────────────────
  const layers = useMemo(() => {
    const result: Layer[] = [];
    const currentFraction = (currentWeek - 1) / 51;

    if (viewMode === "arcs" && arcData.length > 0) {
      result.push(
        new PathLayer({
          id: "migration-arcs",
          data: arcData,
          getPath: (d: ArcDatum) => [d.sourcePosition, d.targetPosition],
          getColor: (d: ArcDatum) => d.color,
          getWidth: (d: ArcDatum) => d.width,
          widthMinPixels: 1,
          widthMaxPixels: 4,
          capRounded: true,
          jointRounded: true,
          opacity: 0.75,
        })
      );
    }

    if (heatmapData.length > 0) {
      result.push(
        new HeatmapLayer({
          id: "migration-traffic",
          data: heatmapData,
          getPosition: (d: HeatmapDatum) => d.position ?? d.coordinates,
          getWeight: (d: HeatmapDatum) => d.weight,
          radiusPixels: 60,
          intensity: 1.5,
          threshold: 0.03,
          colorRange: [
            [68, 1, 84, 0],
            [89, 20, 128, 200],
            [39, 96, 163, 210],
            [31, 158, 137, 220],
            [253, 231, 37, 240],
            [255, 255, 200, 255],
          ],
        })
      );
    }

    if (terminatorCoords.length > 1) {
      result.push(
        new PathLayer({
          id: "terminator",
          data: [{ path: terminatorCoords }],
          getPath: (d: { path: [number, number][] }) => d.path,
          getColor: [255, 80, 80, 200],
          getWidth: 2,
          widthUnits: "pixels",
          getDashArray: [8, 4],
          dashJustified: true,
          extensions: [new PathStyleExtension({ dash: true })],
        })
      );
    }

    if (stationPoints.length > 0) {
      result.push(
        new ScatterplotLayer({
          id: "stations",
          data: stationPoints,
          getPosition: (d: StationDatum) => d.position,
          getFillColor: (d: StationDatum) =>
            d.active ? [0, 200, 100, 255] : [255, 100, 80, 255],
          getRadius: (d: StationDatum) => (d.active ? 6 : 4),
          radiusUnits: "pixels",
          stroked: false,
          pickable: false,
        })
      );
    }

    if (chevrons.length > 0 && showChevrons) {
      const chevronData = chevrons.map((c, i) => ({
        position: [c.lng, c.lat] as [number, number],
        bearing: c.bearing,
        fraction: (i + 1) / (chevrons.length + 1),
      }));
      const [cr, cg, cb] = hexToRgbaArray(speciesColor);
      result.push(
        new IconLayer({
          id: "migration-chevrons",
          data: chevronData,
          getPosition: (d) => d.position,
          getAngle: (d) => d.bearing,
          getSize: 20,
          getColor: (d) => {
            const isBehind = isPlaying && d.fraction < currentFraction;
            return [cr, cg, cb, isBehind ? 64 : 178] as [number, number, number, number];
          },
          iconAtlas: "/icons/arrow.svg",
          iconMapping: { arrow: { x: 0, y: 0, width: 64, height: 64, mask: true } },
          getIcon: () => "arrow",
          billboard: false,
          sizeUnits: "pixels",
          pickable: false,
          updateTriggers: {
            getColor: [isPlaying, currentFraction, speciesColor],
          },
        })
      );
    }

    if (arrowPoints.length > 0) {
      result.push(
        new IconLayer({
          id: "movement-arrows",
          data: arrowPoints,
          getPosition: (d: MovementArrowDatum) => d.position,
          getAngle: (d: MovementArrowDatum) => d.bearing,
          getSize: (d: MovementArrowDatum) => 34 + d.intensity * 46,
          getColor: (d: MovementArrowDatum) => interpolateArrowColor(d.intensity),
          iconAtlas: "/icons/arrow.svg",
          iconMapping: {
            arrow: { x: 0, y: 0, width: 64, height: 64, mask: true },
          },
          getIcon: () => "arrow",
          billboard: false,
          sizeUnits: "pixels",
          pickable: false,
        })
      );
    }

    if (tripData.length > 0) {
      result.push(
        new TripsLayer({
          id: "migration-trips",
          data: tripData,
          getPath: (d: MovebankTrack) => d.path,
          getTimestamps: (d: MovebankTrack) => d.timestamps,
          getColor: [6, 182, 212, 220],
          widthMinPixels: 2,
          capRounded: true,
          jointRounded: true,
          trailLength,
          currentTime,
          opacity: 0.8,
        })
      );
    }

    return result;
  }, [
    arcData,
    arrowPoints,
    chevrons,
    heatmapData,
    isPlaying,
    showChevrons,
    speciesColor,
    stationPoints,
    terminatorCoords,
    tripData,
    viewMode,
    currentTime,
    currentWeek,
    trailLength,
  ]);

  // ── Live position along the arc ───────────────────────────────────────
  const livePosition = useMemo(() => {
    if (!arcCoords || arcCoords.length < 2 || !isPlaying) return null;
    if (cinematicPhase > 0) return null; // suppress during intro
    const fraction = (currentWeek - 1) / 51;
    return pointAlongLine(arcCoords, fraction);
  }, [arcCoords, currentWeek, isPlaying, cinematicPhase]);

  const liveRegionLabel = useMemo(() => {
    if (!livePosition) return null;
    const region = reverseGeocode(livePosition[1], livePosition[0]);
    const weekLabel = `W${String(currentWeek).padStart(2, "0")}`;
    return region ? `${weekLabel} · ${region}` : weekLabel;
  }, [livePosition, currentWeek]);

  return (
    <div
      className="migration-map-shell"
      style={{
        width: "100%",
        height: "100%",
        minHeight: 520,
        position: "relative",
        background: "#000",
      }}
    >
      <DeckGL
        viewState={viewState}
        onViewStateChange={handleViewStateChange}
        controller={true}
        layers={layers}
        useDevicePixels={false}
        style={{ width: "100%", height: "100%" }}
      >
        <Map
          ref={mapRef}
          mapStyle={MAP_STYLE}
          style={{ width: "100%", height: "100%" }}
          attributionControl={false}
          reuseMaps
        >
          <NavigationControl position="top-left" showCompass={false} />

          <MigrationLegend />
          <BirdsInFlightCounter
            value={birdsInFlight}
            label={frameLabel || `W${String(currentWeek).padStart(2, "0")}`}
          />

          {/* ── Origin marker ── */}
          {showOriginMarker && markers?.origin && (
            <Marker
              longitude={markers.origin.lng}
              latitude={markers.origin.lat}
              anchor="center"
            >
              <div
                className="marker-pulse"
                style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}
              >
                <div
                  style={{
                    background: "rgba(11, 15, 20, 0.75)",
                    borderRadius: 10,
                    padding: "2px 8px",
                    whiteSpace: "nowrap",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "11px",
                      color: "#fff",
                      letterSpacing: "0.04em",
                    }}
                  >
                    Breeding grounds
                  </span>
                </div>
                <div
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    background: "#06b6d4",
                    border: "2px solid #fff",
                    boxShadow: "0 0 8px rgba(6, 182, 212, 0.5)",
                  }}
                />
              </div>
            </Marker>
          )}

          {/* ── Destination marker ── */}
          {showDestMarker && markers?.destination && (
            <Marker
              longitude={markers.destination.lng}
              latitude={markers.destination.lat}
              anchor="center"
            >
              <div
                className="marker-pulse"
                style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}
              >
                <div
                  style={{
                    background: "rgba(11, 15, 20, 0.75)",
                    borderRadius: 10,
                    padding: "2px 8px",
                    whiteSpace: "nowrap",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "11px",
                      color: "#f59e0b",
                      letterSpacing: "0.04em",
                    }}
                  >
                    Wintering grounds
                  </span>
                </div>
                <div
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    background: "#f59e0b",
                    border: "2px solid #fff",
                    boxShadow: "0 0 8px rgba(245, 158, 11, 0.5)",
                  }}
                />
              </div>
            </Marker>
          )}

          {/* ── Live position indicator (only after cinematic finishes) ── */}
          {livePosition && isPlaying && (
            <Marker
              longitude={livePosition[0]}
              latitude={livePosition[1]}
              anchor="center"
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ position: "relative", width: 14, height: 14 }}>
                  <div
                    className="live-pulse"
                    style={{
                      position: "absolute",
                      inset: 0,
                      borderRadius: "50%",
                      border: "2px solid #06b6d4",
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      top: 3,
                      left: 3,
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: "#fff",
                    }}
                  />
                </div>
                {liveRegionLabel && (
                  <div
                    style={{
                      background: "rgba(11, 15, 20, 0.8)",
                      borderRadius: 10,
                      padding: "2px 8px",
                      whiteSpace: "nowrap",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "10px",
                        color: "#fff",
                        letterSpacing: "0.04em",
                      }}
                    >
                      {liveRegionLabel}
                    </span>
                  </div>
                )}
              </div>
            </Marker>
          )}
        </Map>
      </DeckGL>
    </div>
  );
}

function hexToRgbaArray(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return [r, g, b];
}

function interpolateArrowColor(t: number): [number, number, number, number] {
  const clamped = Math.max(0, Math.min(1, t));
  return [
    255,
    Math.round(140 + 115 * clamped),
    Math.round(180 * (1 - clamped)),
    Math.round(185 + 70 * clamped),
  ];
}

function isMapViewState(viewState: unknown): viewState is MapViewState {
  if (!viewState || typeof viewState !== "object") return false;
  const candidate = viewState as Partial<MapViewState>;
  return (
    typeof candidate.longitude === "number" &&
    typeof candidate.latitude === "number" &&
    typeof candidate.zoom === "number"
  );
}
