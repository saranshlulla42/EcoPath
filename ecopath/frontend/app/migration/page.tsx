"use client";

import { useState, useEffect, useRef, Suspense, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { GoogleGenerativeAI } from "@google/generative-ai";
import type { ArcDatum, HeatmapDatum, MarkerData, ChevronData } from "@/components/migration/MapCanvas";
import type { SeasonWindow } from "@/components/migration/TimelineScrubber";

const MapCanvas = dynamic(
  () => import("@/components/migration/MapCanvas").then((mod) => mod.MapCanvas),
  { ssr: false }
);
import { SpeciesPanel } from "@/components/migration/SpeciesPanel";
import { MigrationControls } from "@/components/migration/MigrationControls";
import { getRecentObservations, getMigratoryTaxonomy } from "@/lib/ebirdService";
import { getStudiesForSpecies, getTelemetryTracks } from "@/lib/movebankService";
import { aggregateByWeek } from "@/lib/aggregateByWeek";
import { useBirdMigrationData, getInterpolatedFrame } from "@/hooks/useBirdMigrationData";
import { useFrameAnimation } from "@/hooks/useFrameAnimation";
import { useTerminator } from "@/hooks/useTerminator";
import {
  computeOriginDestination,
  computeSeasonWindows,
  pointAlongLine,
  computeBearing,
} from "@/lib/migrationUtils";
import type { EBirdObservation, MigrationSpeciesInfo } from "@/lib/types";
import * as greatCircle from "@turf/great-circle";
import { point } from "@turf/helpers";

const genAI = new GoogleGenerativeAI(process.env.NEXT_PUBLIC_GEMINI_API_KEY ?? "");

function MigrationMapInner() {
  // ── State ────────────────────────────────────────────────────────────────
  // The command bar links here with ?species=<eBird species code>, which is the
  // same canonical id the taxonomy resolver produces, so no mapping is needed.
  const searchParams = useSearchParams();
  const requestedSpecies = searchParams.get("species");

  const [speciesList, setSpeciesList] = useState<MigrationSpeciesInfo[]>([]);
  const [selectedSpecies, setSelectedSpecies] = useState<string>(
    requestedSpecies || "batgod",
  );
  // Set when the link named a species this map cannot show, so the page can say
  // so rather than silently displaying a different bird.
  const [requestedMissing, setRequestedMissing] = useState<string | null>(null);
  const [taxLoading, setTaxLoading] = useState(true);
  const [taxError, setTaxError] = useState<string | null>(null);
  const frameAnimation = useFrameAnimation({ totalFrames: 52, intervalMs: 800 });
  const currentWeek = frameAnimation.currentFrame + 1;
  const isPlaying = frameAnimation.isPlaying;
  const frameProgress = frameAnimation.frameProgress;

  // Gemini narrative state
  const [narrative, setNarrative] = useState<string | null>(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const narrativeCacheRef = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    let mounted = true;
    getMigratoryTaxonomy()
      .then((list) => {
        if (!mounted) return;
        setSpeciesList(list);
        setTaxLoading(false);
        if (!list.length) return;

        if (requestedSpecies) {
          if (list.find((s) => s.speciesCode === requestedSpecies)) {
            setSelectedSpecies(requestedSpecies);
          } else {
            // Falling back to a default here would show one bird's migration
            // under another bird's name.
            setRequestedMissing(requestedSpecies);
            setSelectedSpecies(list[0].speciesCode);
          }
          return;
        }
        if (!list.find((s) => s.speciesCode === "batgod")) {
          setSelectedSpecies(list[0].speciesCode);
        }
      })
      .catch((err) => {
        console.error("[migration] taxonomy load failed:", err);
        if (!mounted) return;
        setTaxError(
          err instanceof Error ? err.message : "Could not load the species list."
        );
        setTaxLoading(false);
      });
    return () => { mounted = false; };
  }, [requestedSpecies]);

  // ── eBird data ──────────────────────────────────────────────────────────
  const { data: ebirdObservations, isLoading: ebirdLoading } = useQuery({
    queryKey: ["ebird-observations", selectedSpecies],
    queryFn: () => getRecentObservations(selectedSpecies, "world", 30),
    enabled: !!selectedSpecies,
    staleTime: 10 * 60 * 1000,
  });

  const trafficData = useBirdMigrationData({
    observations: ebirdObservations,
    currentWeek,
  });

  const terminatorCoords = useTerminator(trafficData.currentFrame?.date);

  const selectedInfo = useMemo(() => {
    const base = speciesList.find((s) => s.speciesCode === selectedSpecies);
    if (!base) return undefined;
    if (!ebirdObservations || ebirdObservations.length === 0) return base;

    let minLat = 90, maxLat = -90;
    let minLatLoc = "", maxLatLoc = "";
    const monthCounts = new Array(12).fill(0);

    for (const obs of ebirdObservations) {
      if (obs.lat < minLat) { minLat = obs.lat; minLatLoc = obs.locationName; }
      if (obs.lat > maxLat) { maxLat = obs.lat; maxLatLoc = obs.locationName; }
      if (obs.date) {
        const d = new Date(obs.date);
        if (!isNaN(d.getTime())) {
          monthCounts[d.getMonth()]++;
        }
      }
    }

    const distanceKm = Math.round(
      Math.acos(
        Math.sin((minLat * Math.PI) / 180) * Math.sin((maxLat * Math.PI) / 180) +
        Math.cos((minLat * Math.PI) / 180) * Math.cos((maxLat * Math.PI) / 180)
      ) * 6371
    );

    const activeMonths = monthCounts
      .map((c, i) => ({ c, i }))
      .filter((x) => x.c > 0)
      .sort((a, b) => b.c - a.c)
      .slice(0, 6)
      .map((x) => x.i + 1);

    return {
      ...base,
      originRegion: minLatLoc || "Unknown",
      destinationRegion: maxLatLoc || "Unknown",
      totalDistanceKm: isNaN(distanceKm) ? 0 : distanceKm,
      activeMonths: activeMonths.length ? activeMonths : [1, 2, 3, 4, 5, 6],
    };
  }, [speciesList, selectedSpecies, ebirdObservations]);

  // ── Movebank data (opt-in) ───────────────────────────────────────────────
  // Movebank aggressively rate-limits (429). Only fetch when the user
  // explicitly requests GPS telemetry tracks via the on-map button.
  const [movebankEnabled, setMovebankEnabled] = useState(false);
  const [movebankError, setMovebankError] = useState(false);

  // Reset opt-in when species changes
  useEffect(() => {
    setMovebankEnabled(false);
    setMovebankError(false);
  }, [selectedSpecies]);

  const { data: movebankStudies, isFetching: movebankStudiesLoading } = useQuery({
    queryKey: ["movebank-studies", selectedInfo?.scientificName],
    queryFn: async () => {
      const result = await getStudiesForSpecies(selectedInfo!.scientificName);
      if (result.length === 0) setMovebankError(true);
      return result;
    },
    enabled: movebankEnabled && !!selectedInfo?.scientificName,
    staleTime: 60 * 60 * 1000,
    retry: 0,
  });

  const firstStudyId = movebankStudies?.[0]?.id;
  const { data: movebankTracks, isFetching: movebankTracksLoading } = useQuery({
    queryKey: ["movebank-tracks", firstStudyId],
    queryFn: () => getTelemetryTracks(firstStudyId!),
    enabled: movebankEnabled && !!firstStudyId,
    staleTime: 60 * 60 * 1000,
    retry: 0,
  });

  const movebankLoading = movebankStudiesLoading || movebankTracksLoading;

  // ── Weekly aggregation ──────────────────────────────────────────────────
  const weeklyData = useMemo(() => {
    if (!ebirdObservations?.length) return new Map<number, EBirdObservation[]>();
    return aggregateByWeek(ebirdObservations);
  }, [ebirdObservations]);

  const currentWeekObservations = weeklyData.get(currentWeek) ?? [];

  // ── Bounding box for auto-zoom ──────────────────────────────────────────
  const flyToBounds = useMemo<[number, number, number, number] | null>(() => {
    if (!ebirdObservations || ebirdObservations.length === 0) return null;

    const breeding = collectWeekObservations(weeklyData, 20, 32);
    const wintering = [
      ...collectWeekObservations(weeklyData, 44, 52),
      ...collectWeekObservations(weeklyData, 1, 8),
    ];
    const seasonal = [...breeding, ...wintering];
    const boundsSource = seasonal.length >= 2 ? seasonal : ebirdObservations;

    let minLng = 180, maxLng = -180, minLat = 90, maxLat = -90;
    for (const obs of boundsSource) {
      if (obs.lng < minLng) minLng = obs.lng;
      if (obs.lng > maxLng) maxLng = obs.lng;
      if (obs.lat < minLat) minLat = obs.lat;
      if (obs.lat > maxLat) maxLat = obs.lat;
    }

    const lngPad = Math.max((maxLng - minLng) * 0.1, 2);
    const latPad = Math.max((maxLat - minLat) * 0.1, 2);

    return [
      Math.max(-180, minLng - lngPad),
      Math.max(-85, minLat - latPad),
      Math.min(180, maxLng + lngPad),
      Math.min(85, maxLat + latPad),
    ];
  }, [ebirdObservations, weeklyData]);

  // ── Origin / destination markers ────────────────────────────────────────
  const markerData = useMemo<MarkerData | null>(() => {
    if (weeklyData.size === 0) return null;
    return computeOriginDestination(weeklyData);
  }, [weeklyData]);

  // ── Season windows ──────────────────────────────────────────────────────
  const seasonWindows = useMemo<SeasonWindow | null>(() => {
    if (weeklyData.size === 0) return null;
    return computeSeasonWindows(weeklyData);
  }, [weeklyData]);

  // ── Great-circle arc and chevrons ───────────────────────────────────────
  const { arcCoords, chevrons } = useMemo<{
    arcCoords: [number, number][] | null;
    chevrons: ChevronData[];
  }>(() => {
    if (!markerData?.origin || !markerData?.destination) {
      return { arcCoords: null, chevrons: [] };
    }
    const { origin, destination } = markerData;
    try {
      const gc = greatCircle.default(
        point([origin.lng, origin.lat]),
        point([destination.lng, destination.lat]),
        { npoints: 50 }
      );
      if (gc.geometry.type === "LineString") {
        const coords = gc.geometry.coordinates as [number, number][];
        // Compute 4 chevrons at 20%, 40%, 60%, 80%
        const chevs: ChevronData[] = [];
        for (const frac of [0.2, 0.4, 0.6, 0.8]) {
          const pos = pointAlongLine(coords, frac);
          // Get nearby point for bearing
          const posAhead = pointAlongLine(coords, Math.min(frac + 0.02, 1));
          const bearing = computeBearing(pos[1], pos[0], posAhead[1], posAhead[0]);
          chevs.push({ lng: pos[0], lat: pos[1], bearing });
        }
        return { arcCoords: coords, chevrons: chevs };
      }
    } catch {
      // fallback — no chevrons
    }
    return { arcCoords: null, chevrons: [] };
  }, [markerData]);

  // ── Compute arc data (great-circle paths) ──────────────────────────────
  const arcData: ArcDatum[] = (() => {
    if (currentWeekObservations.length < 2) return [];

    const arcs: ArcDatum[] = [];
    const sorted = [...currentWeekObservations].sort(
      (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
    );

    for (let i = 0; i < sorted.length - 1; i++) {
      const src = sorted[i];
      const dst = sorted[i + 1];

      if (
        Math.abs(src.lat - dst.lat) < 0.01 &&
        Math.abs(src.lng - dst.lng) < 0.01
      )
        continue;

      try {
        const gc = greatCircle.default(
          point([src.lng, src.lat]),
          point([dst.lng, dst.lat]),
          { npoints: 50 }
        );
        if (gc.geometry.type === "LineString") {
          const coords = gc.geometry.coordinates as [number, number][];
          for (let j = 0; j < coords.length - 1; j++) {
            arcs.push({
              sourcePosition: coords[j],
              targetPosition: coords[j + 1],
              color: hexToRgba(selectedInfo?.color ?? "#06b6d4", 180),
              width: 2,
            });
          }
        }
      } catch {
        arcs.push({
          sourcePosition: [src.lng, src.lat],
          targetPosition: [dst.lng, dst.lat],
          color: hexToRgba(selectedInfo?.color ?? "#06b6d4", 180),
          width: 2,
        });
      }
    }

    return arcs;
  })();

  // ── Heatmap data ────────────────────────────────────────────────────────
  const heatmapData: HeatmapDatum[] = useMemo(() => {
    return getInterpolatedFrame(
      trafficData.currentFramePoints,
      trafficData.nextFramePoints,
      frameProgress
    );
  }, [trafficData.currentFramePoints, trafficData.nextFramePoints, frameProgress]);

  const birdsInFlight = trafficData.birdsInFlight * (1 - frameProgress) + 
                        trafficData.nextBirdsInFlight * frameProgress;

  // ── Trip animation time ─────────────────────────────────────────────────
  const tripTimeRange = (() => {
    if (!movebankTracks?.length) return { min: 0, max: 0 };
    let min = Infinity, max = -Infinity;
    for (const track of movebankTracks) {
      for (const ts of track.timestamps) {
        if (ts < min) min = ts;
        if (ts > max) max = ts;
      }
    }
    return { min, max };
  })();

  const currentTripTime =
    tripTimeRange.min +
    ((currentWeek - 1) / 51) * (tripTimeRange.max - tripTimeRange.min);

  const handlePlayToggle = () => {
    if (isPlaying) frameAnimation.pause();
    else frameAnimation.play();
  };

  const handleWeekChange = (week: number) => {
    frameAnimation.pause();
    frameAnimation.setFrame(week - 1);
  };

  const handleSpeciesChange = (code: string) => {
    setSelectedSpecies(code);
    frameAnimation.pause();
    frameAnimation.reset();
  };

  const handlePrevFrame = () => {
    frameAnimation.pause();
    frameAnimation.prev();
  };

  const handleNextFrame = () => {
    frameAnimation.pause();
    frameAnimation.next();
  };

  const handleResetFrames = () => {
    frameAnimation.pause();
    frameAnimation.reset();
  };

  // ── Gemini narrative fetch ──────────────────────────────────────────────
  useEffect(() => {
    if (!selectedInfo || !ebirdObservations?.length) {
      setNarrative(null);
      return;
    }

    const speciesCode = selectedInfo.speciesCode;

    // Check cache
    if (narrativeCacheRef.current.has(speciesCode)) {
      setNarrative(narrativeCacheRef.current.get(speciesCode)!);
      return;
    }

    let cancelled = false;
    setNarrativeLoading(true);
    setNarrative(null);

    (async () => {
      try {
        const obs = ebirdObservations;
        let minLat = 90, maxLat = -90, minLng = 180, maxLng = -180;
        const weekCounts: Record<number, number> = {};
        for (const o of obs) {
          if (o.lat < minLat) minLat = o.lat;
          if (o.lat > maxLat) maxLat = o.lat;
          if (o.lng < minLng) minLng = o.lng;
          if (o.lng > maxLng) maxLng = o.lng;
          if (o.date) {
            const d = new Date(o.date);
            if (!isNaN(d.getTime())) {
              const w = Math.ceil((d.getTime() - new Date(d.getFullYear(), 0, 1).getTime()) / 604800000);
              weekCounts[w] = (weekCounts[w] || 0) + (o.count || 1);
            }
          }
        }

        const sortedWeeks = Object.entries(weekCounts)
          .sort(([, a], [, b]) => b - a);
        const top3Weeks = sortedWeeks.slice(0, 3).map(([w]) => `W${w}`).join(", ");
        const bottom3Weeks = sortedWeeks.slice(-3).map(([w]) => `W${w}`).join(", ");

        const od = markerData;
        const originLat = od?.origin?.lat?.toFixed(1) ?? "N/A";
        const originLng = od?.origin?.lng?.toFixed(1) ?? "N/A";
        const destLat = od?.destination?.lat?.toFixed(1) ?? "N/A";
        const destLng = od?.destination?.lng?.toFixed(1) ?? "N/A";

        const prompt = `You are a field ornithologist writing a concise migration briefing for a nature intelligence app.
Species: ${selectedInfo.commonName} (${selectedInfo.scientificName})
Observation data summary:

Total observations loaded: ${obs.length}
Geographic spread: ${minLat.toFixed(1)}°–${maxLat.toFixed(1)}° latitude, ${minLng.toFixed(1)}°–${maxLng.toFixed(1)}° longitude
Peak observation weeks: ${top3Weeks}
Low observation weeks: ${bottom3Weeks}
Origin centroid: ${originLat}, ${originLng}
Destination centroid: ${destLat}, ${destLng}

Write 3–4 sentences only. Cover: where this species breeds and winters, the general direction and timing of migration, and one interesting or unusual fact about this species' journey. Do not mention data sources. Do not use the word "migration" more than once. Write in present tense. Plain prose, no bullet points.`;

        const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
        const result = await model.generateContent([prompt]);
        const text = result.response.text();

        if (!cancelled) {
          narrativeCacheRef.current.set(speciesCode, text);
          setNarrative(text);
        }
      } catch {
        if (!cancelled) setNarrative(null);
      } finally {
        if (!cancelled) setNarrativeLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [selectedInfo, ebirdObservations, markerData]);

  // ── Loading state ───────────────────────────────────────────────────────
  const isInitialLoading = ebirdLoading && !ebirdObservations;

  return (
    <div
      style={{
        paddingTop: 52,
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "var(--background)",
      }}
    >
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* ── Species panel ──────────────────────────────────────────── */}
        <SpeciesPanel
          speciesList={speciesList}
          selectedSpeciesCode={selectedSpecies}
          onSelectSpecies={handleSpeciesChange}
          isLoading={taxLoading}
          loadError={
            taxError ??
            (requestedMissing
              ? `“${requestedMissing}” is not in this map’s migratory species list, ` +
                `so a different species is shown. This map covers eBird’s migratory orders only.`
              : null)
          }
          narrative={narrative}
          narrativeLoading={narrativeLoading}
          iucnStatus={null}
        />

        {/* ── Map area ───────────────────────────────────────────────── */}
        <div
          className="migration-workspace"
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            minWidth: 0,
            minHeight: 0,
          }}
        >
          <div
            style={{
              flex: 1,
              position: "relative",
              minHeight: 520,
              overflow: "hidden",
              background: "#000",
            }}
          >
            {isInitialLoading ? (
              <div
                style={{
                  width: "100%",
                  height: "100%",
                  minHeight: 520,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: "var(--map-chrome)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 12,
                  }}
                >
                  <div
                    style={{
                      width: 16,
                      height: 16,
                      border: "1.5px solid var(--accent-data)",
                      borderTopColor: "transparent",
                      borderRadius: "50%",
                      animation: "spin 0.7s linear infinite",
                    }}
                  />
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.62rem",
                      letterSpacing: "0.15em",
                      textTransform: "uppercase",
                      color: "var(--map-chrome-text-2)",
                      fontWeight: 500,
                    }}
                  >
                    Loading migration data
                  </span>
                </div>
              </div>
            ) : (
              <MapCanvas
                arcData={arcData}
                heatmapData={heatmapData}
                tripData={movebankTracks ?? []}
                viewMode="arcs"
                currentTime={currentTripTime}
                flyToBounds={flyToBounds}
                markers={markerData}
                arcCoords={arcCoords}
                chevrons={chevrons}
                arrowPoints={trafficData.arrowPoints}
                stationPoints={trafficData.stationPoints}
                terminatorCoords={terminatorCoords}
                birdsInFlight={birdsInFlight}
                frameLabel={trafficData.currentFrame?.label}
                currentWeek={currentWeek}
                isPlaying={isPlaying}
                speciesColor={selectedInfo?.color ?? "#06b6d4"}
                speciesKey={selectedSpecies}
                onZoomStart={() => frameAnimation.pause()}
                onZoomEnd={() => frameAnimation.play()}
              />
            )}

            {/* ── Loading overlay (subsequent fetches) ───────────────── */}
            {ebirdLoading && ebirdObservations && (
              <div
                style={{
                  position: "absolute",
                  top: 12,
                  left: "50%",
                  transform: "translateX(-50%)",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  background: "var(--map-chrome-soft)",
                  border: "1px solid rgba(91, 184, 154, 0.3)",
                  borderRadius: "var(--r-md)",
                  padding: "0.4rem 0.85rem",
                  zIndex: 20,
                  backdropFilter: "blur(4px)",
                  WebkitBackdropFilter: "blur(4px)",
                }}
              >
                <div
                  style={{
                    width: 8,
                    height: 8,
                    border: "1px solid var(--accent-data)",
                    borderTopColor: "transparent",
                    borderRadius: "50%",
                    animation: "spin 0.7s linear infinite",
                  }}
                />
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.6rem",
                    letterSpacing: "0.12em",
                    color: "var(--map-chrome-text-2)",
                    textTransform: "uppercase",
                    fontWeight: 500,
                  }}
                >
                  Refreshing data
                </span>
              </div>
            )}

            {/* ── Observation count badge ──────────────────────────────── */}
            {currentWeekObservations.length > 0 && (
              <div
                style={{
                  position: "absolute",
                  top: 58,
                  left: 12,
                  background: "var(--map-chrome-soft)",
                  border: "1px solid rgba(91, 184, 154, 0.3)",
                  borderRadius: "var(--r-md)",
                  padding: "0.45rem 0.7rem",
                  zIndex: 10,
                  pointerEvents: "none",
                  backdropFilter: "blur(4px)",
                  WebkitBackdropFilter: "blur(4px)",
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.65rem",
                    color: "var(--accent-data)",
                    fontWeight: 600,
                  }}
                >
                  {currentWeekObservations.length}
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.58rem",
                    color: "var(--map-chrome-text-2)",
                    marginLeft: 6,
                  }}
                >
                  observations · W{String(currentWeek).padStart(2, "0")}
                </span>
              </div>
            )}

            {/* ── Movebank GPS tracks button ──────────────────────────── */}
            {!movebankEnabled && !isInitialLoading && (
              <button
                onClick={() => { setMovebankEnabled(true); setMovebankError(false); }}
                style={{
                  position: "absolute",
                  bottom: 16,
                  right: 16,
                  background: "transparent",
                  border: "1px solid var(--accent-data)",
                  borderRadius: "var(--r-md)",
                  padding: "0.5rem 0.85rem",
                  zIndex: 10,
                  cursor: "pointer",
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  color: "var(--accent-data)",
                  transition: "background 140ms ease",
                  fontWeight: 500,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "rgba(91, 184, 154, 0.1)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                }}
              >
                Load GPS Tracks
              </button>
            )}
            {movebankEnabled && movebankLoading && (
              <div
                style={{
                  position: "absolute",
                  bottom: 16,
                  right: 16,
                  background: "var(--map-chrome-soft)",
                  border: "1px solid rgba(91, 184, 154, 0.3)",
                  borderRadius: "var(--r-md)",
                  padding: "0.5rem 0.85rem",
                  zIndex: 10,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  backdropFilter: "blur(4px)",
                  WebkitBackdropFilter: "blur(4px)",
                }}
              >
                <div
                  style={{
                    width: 8,
                    height: 8,
                    border: "1px solid var(--accent-data)",
                    borderTopColor: "transparent",
                    borderRadius: "50%",
                    animation: "spin 0.7s linear infinite",
                  }}
                />
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.6rem",
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    color: "var(--map-chrome-text-2)",
                    fontWeight: 500,
                  }}
                >
                  Loading GPS tracks
                </span>
              </div>
            )}
            {movebankEnabled && !movebankLoading && movebankError && (
              <div
                style={{
                  position: "absolute",
                  bottom: 16,
                  right: 16,
                  background: "var(--map-chrome-soft)",
                  border: "1px solid rgba(91, 184, 154, 0.3)",
                  borderRadius: "var(--r-md)",
                  padding: "0.5rem 0.85rem",
                  zIndex: 10,
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  color: "var(--map-chrome-text-3)",
                  fontWeight: 500,
                  backdropFilter: "blur(4px)",
                  WebkitBackdropFilter: "blur(4px)",
                }}
              >
                No GPS tracks available
              </div>
            )}
          </div>

          <MigrationControls
            currentWeek={currentWeek}
            isPlaying={isPlaying}
            onWeekChange={handleWeekChange}
            onPlayToggle={handlePlayToggle}
            onPrev={handlePrevFrame}
            onNext={handleNextFrame}
            onReset={handleResetFrames}
            seasonWindows={seasonWindows}
            speciesColor={selectedInfo?.color ?? "#06b6d4"}
            dates={trafficData.availableDates}
          />
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ── Utility ────────────────────────────────────────────────────────────────

function hexToRgba(
  hex: string,
  alpha: number
): [number, number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return [r, g, b, alpha];
}

function collectWeekObservations(
  weeklyData: Map<number, EBirdObservation[]>,
  startWeek: number,
  endWeek: number
) {
  const observations: EBirdObservation[] = [];
  for (let week = startWeek; week <= endWeek; week++) {
    observations.push(...(weeklyData.get(week) ?? []));
  }
  return observations;
}

// ── Page export ────────────────────────────────────────────────────────────

export default function MigrationPage() {
  return (
    <Suspense
      fallback={
        <div
          style={{
            paddingTop: 52,
            height: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--background)",
          }}
        >
          <div
            style={{
              width: 12,
              height: 12,
              border: "1.5px solid var(--accent-primary)",
              borderTopColor: "transparent",
              borderRadius: "50%",
              animation: "spin 0.7s linear infinite",
            }}
          />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      }
    >
      <MigrationMapInner />
    </Suspense>
  );
}
