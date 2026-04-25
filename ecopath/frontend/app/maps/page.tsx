"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Map, { Layer, Source, Popup, type MapRef } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  getGBIFHeatmapData,
  getGBIFHeatmapTimeline,
  getMigrationRoutes,
  searchSpecies,
  getGBIFSpeciesDetail,
} from "@/lib/api";
import { Play, Pause, RotateCcw } from "lucide-react";
import type { GBIFSearchResult } from "@/lib/types";
import { COUNTRY_OPTIONS } from "@/lib/countries";

const MAP_STYLE = process.env.NEXT_PUBLIC_MAP_STYLE || "https://tiles.openfreemap.org/styles/dark";

// ── Heatmap layer — warm amber/crimson palette ─────────────────────────────
const HEATMAP_LAYER = {
  id: "heatmap-layer",
  type: "heatmap" as const,
  paint: {
    "heatmap-weight": ["interpolate", ["linear"], ["get", "count"], 0, 0, 10, 1] as unknown as number,
    "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 0, 1, 9, 3] as unknown as number,
    "heatmap-color": [
      "interpolate", ["linear"], ["heatmap-density"],
      0,   "rgba(0,0,0,0)",
      0.2, "rgba(180,140,80,0.35)",
      0.4, "rgba(201,130,64,0.65)",
      0.65,"rgba(185,78,40,0.82)",
      0.85,"rgba(160,38,38,0.92)",
      1,   "rgba(148,28,28,1.0)",
    ] as unknown as string,
    "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 0, 10, 9, 32] as unknown as number,
    "heatmap-opacity": 0.88,
  },
} as const;

// ── Migration layers — amber routes on dark map ────────────────────────────
const MIGRATION_LINE_LAYER = {
  id: "migration-line",
  type: "line" as const,
  paint: {
    "line-color": "#c98240",
    "line-width": 1.5,
    "line-opacity": 0.7,
    "line-dasharray": [3, 2],
  },
};

const MIGRATION_POINT_LAYER = {
  id: "migration-waypoints",
  type: "circle" as const,
  paint: {
    "circle-radius": 4,
    "circle-color": "#c98240",
    "circle-stroke-width": 1.5,
    "circle-stroke-color": "#0d0b08",
    "circle-opacity": 0.85,
  },
};

interface MapSpecies {
  gbif_key: number;
  common_name: string;
  scientific_name: string;
  family?: string;
}

function MapsPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const mapRef = useRef<MapRef>(null);

  const [selectedSpecies, setSelectedSpecies] = useState<MapSpecies | null>(null);
  const [selectedCountry, setSelectedCountry] = useState<string>("GLOBAL");
  const [activeTab, setActiveTab] = useState<"heatmap" | "migration">("heatmap");
  const [year, setYear] = useState(2024);
  const [searchQ, setSearchQ] = useState("");
  const [searchResults, setSearchResults] = useState<GBIFSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [animating, setAnimating] = useState(false);
  const [animFrame, setAnimFrame] = useState(0);
  const [popupInfo, setPopupInfo] = useState<{ lng: number; lat: number; count: number; state: string; year: number } | null>(null);
  const animRef = useRef<NodeJS.Timeout | undefined>(undefined);
  const debounceRef = useRef<NodeJS.Timeout | undefined>(undefined);

  const speciesParam = searchParams.get("species");
  const [paramLoaded, setParamLoaded] = useState(false);

  const { data: paramSpeciesDetail } = useQuery({
    queryKey: ["gbif-species-for-map", speciesParam],
    queryFn: () => getGBIFSpeciesDetail(speciesParam!),
    enabled: !!speciesParam && !paramLoaded,
  });

  useEffect(() => {
    if (paramSpeciesDetail && !paramLoaded) {
      const sp: MapSpecies = {
        gbif_key: paramSpeciesDetail.key ?? parseInt(speciesParam!, 10),
        common_name: paramSpeciesDetail.vernacularName ?? paramSpeciesDetail.canonicalName ?? paramSpeciesDetail.scientificName ?? "Unknown",
        scientific_name: paramSpeciesDetail.canonicalName ?? paramSpeciesDetail.scientificName ?? "",
        family: paramSpeciesDetail.family,
      };
      setSelectedSpecies(sp);
      setSearchQ(sp.common_name);
      setParamLoaded(true);
      const countryOpt = COUNTRY_OPTIONS.find(c => c.code === selectedCountry) ?? COUNTRY_OPTIONS[1];
      mapRef.current?.flyTo({ center: countryOpt.center, zoom: countryOpt.zoom, duration: 1200 });
    }
  }, [paramSpeciesDetail, paramLoaded, speciesParam]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (activeTab !== "heatmap") return;
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowLeft")  { e.preventDefault(); setYear(p => Math.max(2014, p - 1)); }
      if (e.key === "ArrowRight") { e.preventDefault(); setYear(p => Math.min(2024, p + 1)); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeTab]);

  useEffect(() => {
    const scroller = document.getElementById("year-scroller");
    const activeBtn = scroller?.querySelector(`[data-year="${year}"]`) as HTMLElement;
    if (activeBtn && scroller) activeBtn.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, [year]);

  const { data: heatmapData, isLoading: heatmapLoading } = useQuery({
    queryKey: ["gbif-heatmap", selectedSpecies?.gbif_key, year, selectedCountry],
    queryFn: () => getGBIFHeatmapData(selectedSpecies!.gbif_key, year, selectedCountry),
    enabled: !!selectedSpecies?.gbif_key && activeTab === "heatmap",
  });

  const { data: timeline } = useQuery({
    queryKey: ["gbif-heatmap-timeline", selectedSpecies?.gbif_key, selectedCountry],
    queryFn: () => getGBIFHeatmapTimeline(selectedSpecies!.gbif_key, selectedCountry),
    enabled: !!selectedSpecies?.gbif_key,
  });

  const { data: migrationData } = useQuery({
    queryKey: ["migration", selectedSpecies?.gbif_key],
    queryFn: () => getMigrationRoutes(String(selectedSpecies!.gbif_key)),
    enabled: !!selectedSpecies?.gbif_key && activeTab === "migration",
  });

  const handleSearch = (val: string) => {
    setSearchQ(val);
    clearTimeout(debounceRef.current);
    if (val.length < 2) { setSearchResults([]); return; }
    debounceRef.current = setTimeout(async () => {
      setSearchLoading(true);
      try { const data = await searchSpecies(val); setSearchResults(data); }
      finally { setSearchLoading(false); }
    }, 300);
  };

  const selectSpecies = (s: GBIFSearchResult) => {
    setSelectedSpecies({ gbif_key: s.gbif_key, common_name: s.common_name, scientific_name: s.scientific_name, family: s.family });
    setSearchResults([]);
    setSearchQ(s.common_name);
    setPopupInfo(null);
    const countryOpt = COUNTRY_OPTIONS.find(c => c.code === selectedCountry) ?? COUNTRY_OPTIONS[1];
    mapRef.current?.flyTo({ center: countryOpt.center, zoom: countryOpt.zoom, duration: 1200 });
  };

  const handleCountryChange = (code: string) => {
    setSelectedCountry(code);
    setPopupInfo(null);
    const opt = COUNTRY_OPTIONS.find(c => c.code === code);
    if (opt) mapRef.current?.flyTo({ center: opt.center, zoom: opt.zoom, duration: 1200 });
  };

  const toggleAnimation = () => {
    if (animating) { clearInterval(animRef.current); setAnimating(false); return; }
    const waypoints = migrationData?.routes?.[0]?.waypoints ?? [];
    if (!waypoints.length) return;
    setAnimating(true); setAnimFrame(0);
    let i = 0;
    animRef.current = setInterval(() => {
      i++;
      if (i >= waypoints.length) { clearInterval(animRef.current); setAnimating(false); setAnimFrame(0); return; }
      setAnimFrame(i);
      mapRef.current?.flyTo({ center: [waypoints[i].lng, waypoints[i].lat], zoom: 5, duration: 800, essential: true });
    }, 1200);
  };

  const years = Array.from({ length: 11 }, (_, i) => 2014 + i);
  const maxTimelineVal = Math.max(...years.map(y => timeline?.timeline?.[y]?.total ?? 0), 1);

  const animWaypoint = animating ? migrationData?.routes?.[0]?.waypoints?.[animFrame] : null;
  const animPointGeoJSON: GeoJSON.FeatureCollection = animWaypoint
    ? { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Point", coordinates: [animWaypoint.lng, animWaypoint.lat] }, properties: { name: animWaypoint.location_name } }] }
    : { type: "FeatureCollection", features: [] };

  // ── Sidebar width ──
  const SIDEBAR_W = 260;

  return (
    <div style={{ paddingTop: 52, height: "100vh", display: "flex", flexDirection: "column", background: "var(--background)" }}>
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* ── Left panel — light surface ────────────────────────────────── */}
        <div style={{
          width: SIDEBAR_W,
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          background: "var(--surface)",
          borderRight: "1px solid var(--border)",
          overflowY: "auto",
          zIndex: 10,
        }}>

          {/* Region */}
          <div style={{ padding: "1rem 1rem 0.85rem", borderBottom: "1px solid var(--border-subtle)" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "0.5rem", fontWeight: 500 }}>Region</p>
            <div style={{ position: "relative" }}>
              <select
                value={selectedCountry}
                onChange={e => handleCountryChange(e.target.value)}
                style={{
                  width: "100%",
                  background: "var(--surface-raised)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--r-md)",
                  color: "var(--text-primary)",
                  fontFamily: "var(--font-sans)",
                  fontSize: "0.85rem",
                  padding: "0.45rem 1.4rem 0.45rem 0.7rem",
                  outline: "none",
                  cursor: "pointer",
                  appearance: "none",
                }}
              >
                {COUNTRY_OPTIONS.map(opt => <option key={opt.code} value={opt.code}>{opt.name}</option>)}
              </select>
              <span style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", fontFamily: "var(--font-mono)", fontSize: "0.55rem", color: "var(--text-tertiary)", pointerEvents: "none" }}>▼</span>
            </div>
          </div>

          {/* Search */}
          <div style={{ padding: "0.85rem 1rem", borderBottom: "1px solid var(--border-subtle)" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "0.5rem", fontWeight: 500 }}>Species</p>
            <div style={{ position: "relative" }}>
              <input
                type="text"
                value={searchQ}
                onChange={e => handleSearch(e.target.value)}
                placeholder="Search birds…"
                id="map-species-search"
                style={{
                  width: "100%",
                  background: "var(--surface-raised)",
                  border: `1px solid ${searchQ ? "var(--accent-primary)" : "var(--border)"}`,
                  borderRadius: "var(--r-md)",
                  color: "var(--text-primary)",
                  fontFamily: "var(--font-sans)",
                  fontSize: "0.85rem",
                  padding: "0.45rem 1.6rem 0.45rem 0.7rem",
                  outline: "none",
                  transition: "border-color 140ms ease",
                }}
              />
              {searchLoading && (
                <div style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", width: 10, height: 10, border: "1px solid var(--accent-primary)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
              )}
            </div>

            {/* Search results */}
            {searchResults.length > 0 && (
              <div style={{ marginTop: "0.6rem", border: "1px solid var(--border)", borderRadius: "var(--r-md)", overflow: "hidden", background: "var(--surface-raised)", boxShadow: "var(--shadow-card)" }}>
                {searchResults.map((s, i) => (
                  <button key={s.gbif_key} onClick={() => selectSpecies(s)}
                    style={{
                      width: "100%",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "flex-start",
                      gap: 1,
                      padding: "0.55rem 0.75rem",
                      background: "transparent",
                      border: "none",
                      borderTop: i > 0 ? "1px solid var(--border-subtle)" : "none",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "background 120ms ease",
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-muted)")}
                    onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                  >
                    <span style={{ fontFamily: "var(--font-sans)", fontSize: "0.82rem", color: "var(--text-primary)", fontWeight: 500 }}>{s.common_name}</span>
                    <span style={{ fontFamily: "var(--font-sans)", fontSize: "0.72rem", fontStyle: "italic", color: "var(--text-secondary)" }}>{s.scientific_name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Species info */}
          {selectedSpecies ? (
            <div style={{ padding: "1rem", flex: 1 }}>
              <p style={{ fontFamily: "var(--font-display)", fontSize: "1.05rem", fontWeight: 600, color: "var(--text-primary)", lineHeight: 1.15, marginBottom: "0.15rem", letterSpacing: "-0.005em" }}>
                {selectedSpecies.common_name}
              </p>
              <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.75rem", fontStyle: "italic", color: "var(--text-secondary)", marginBottom: "0.4rem" }}>
                {selectedSpecies.scientific_name}
              </p>
              {selectedSpecies.family && (
                <span style={{ display: "inline-block", fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--accent-primary)", background: "var(--accent-muted)", padding: "2px 8px", borderRadius: "var(--r-sm)", marginBottom: "1rem", fontWeight: 500 }}>
                  {selectedSpecies.family}
                </span>
              )}

              {/* Timeline mini bars */}
              {timeline?.timeline && (
                <div style={{ marginBottom: "0.85rem" }}>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "0.5rem", fontWeight: 500 }}>
                    Occurrence trend
                  </p>
                  <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 28 }}>
                    {years.map(yr => {
                      const val = timeline.timeline[yr]?.total ?? 0;
                      const pct = maxTimelineVal > 0 ? (val / maxTimelineVal) * 100 : 0;
                      const isActive = yr === year;
                      return (
                        <div
                          key={yr}
                          title={`${yr}: ${val.toLocaleString()}`}
                          onClick={() => setYear(yr)}
                          style={{
                            flex: 1,
                            height: `${Math.max(6, pct)}%`,
                            background: isActive ? "var(--accent-primary)" : "var(--border)",
                            borderRadius: 1,
                            cursor: "pointer",
                            transition: "background 120ms ease, height 200ms ease",
                          }}
                        />
                      );
                    })}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 3 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", color: "var(--text-tertiary)" }}>2014</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", color: "var(--text-tertiary)" }}>2024</span>
                  </div>
                </div>
              )}

              <button
                onClick={() => router.push(`/species/${selectedSpecies.gbif_key}`)}
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.62rem",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  color: "var(--text-on-accent)",
                  background: "var(--accent-primary)",
                  border: "none",
                  borderRadius: "var(--r-md)",
                  cursor: "pointer",
                  padding: "0.6rem 1rem",
                  width: "100%",
                  transition: "background 140ms ease",
                  fontWeight: 500,
                }}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-secondary)")}
                onMouseLeave={e => (e.currentTarget.style.background = "var(--accent-primary)")}
              >
                Full profile →
              </button>
            </div>
          ) : (
            <div style={{ padding: "1.5rem 1rem", flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.8rem", fontStyle: "italic", color: "var(--text-tertiary)", textAlign: "center", lineHeight: 1.5 }}>
                Search for a species to begin exploring
              </p>
            </div>
          )}
        </div>

        {/* ── Map area ──────────────────────────────────────────────────── */}
        <div style={{ flex: 1, position: "relative" }}>
          <Map
            ref={mapRef}
            mapStyle={MAP_STYLE}
            initialViewState={{ longitude: 20, latitude: 15, zoom: 1.8 }}
            style={{ width: "100%", height: "100%" }}
            interactiveLayerIds={activeTab === "heatmap" ? ["heatmap-circle-layer"] : []}
            onClick={e => {
              if (activeTab !== "heatmap") return;
              const feature = e.features?.[0];
              if (feature && feature.geometry.type === "Point") {
                const [lng, lat] = (feature.geometry as GeoJSON.Point).coordinates;
                setPopupInfo({ lng, lat, count: feature.properties?.count ?? 1, state: feature.properties?.state ?? "Unknown", year: feature.properties?.year ?? year });
              }
            }}
          >
            {/* Heatmap */}
            {activeTab === "heatmap" && heatmapData?.geojson && (
              <Source id="heatmap-source" type="geojson" data={heatmapData.geojson}>
                {/* @ts-ignore */}
                <Layer {...HEATMAP_LAYER} />
                <Layer id="heatmap-circle-layer" type="circle"
                  paint={{
                    "circle-radius": ["interpolate", ["linear"], ["zoom"], 0, 1, 9, 5] as unknown as number,
                    "circle-color": "rgba(201,130,64,0.3)",
                    "circle-stroke-width": 0,
                    "circle-opacity": ["interpolate", ["linear"], ["zoom"], 0, 0, 7, 0, 9, 0.5] as unknown as number,
                  }} />
              </Source>
            )}

            {/* Click popup */}
            {popupInfo && (
              <Popup longitude={popupInfo.lng} latitude={popupInfo.lat}
                onClose={() => setPopupInfo(null)} closeOnClick={false} anchor="bottom" offset={8}>
                <div style={{ fontFamily: "var(--font-serif)", color: "#1a1812", padding: "2px 0", fontSize: 13 }}>
                  <p style={{ fontWeight: 600, marginBottom: 3, fontFamily: "var(--font-display)", fontSize: 14 }}>
                    {selectedSpecies?.common_name}
                  </p>
                  <p style={{ fontSize: 12, color: "#5a4a35", marginBottom: 1 }}>
                    {popupInfo.count} {popupInfo.count === 1 ? "record" : "records"}
                  </p>
                  <p style={{ fontSize: 11, color: "#8a7a64" }}>{popupInfo.state}</p>
                  <p style={{ fontSize: 11, color: "#8a7a64" }}>{popupInfo.year}</p>
                  <p style={{ fontSize: 10, color: "#b0a08c", marginTop: 3, fontFamily: "var(--font-mono)" }}>
                    {popupInfo.lat.toFixed(3)}, {popupInfo.lng.toFixed(3)}
                  </p>
                </div>
              </Popup>
            )}

            {/* Migration routes */}
            {activeTab === "migration" && migrationData?.routes?.map((route: any) =>
              route.geojson ? (
                <Source key={route.id} id={`route-${route.id}`} type="geojson" data={route.geojson}>
                  <Layer {...MIGRATION_LINE_LAYER} id={`line-${route.id}`} />
                  <Source id={`wp-${route.id}`} type="geojson" data={{
                    type: "FeatureCollection",
                    features: route.waypoints.map((wp: any) => ({
                      type: "Feature",
                      geometry: { type: "Point", coordinates: [wp.lng, wp.lat] },
                      properties: { name: wp.location_name, month: wp.month },
                    })),
                  }}>
                    <Layer {...MIGRATION_POINT_LAYER} id={`wp-layer-${route.id}`} />
                  </Source>
                </Source>
              ) : null
            )}

            {/* Animated dot */}
            {animWaypoint && (
              <Source id="anim-point" type="geojson" data={animPointGeoJSON}>
                <Layer id="anim-dot" type="circle"
                  paint={{ "circle-radius": 10, "circle-color": "var(--accent-primary)", "circle-opacity": 0.9, "circle-stroke-width": 2, "circle-stroke-color": "var(--bg-primary)" }} />
              </Source>
            )}
          </Map>

          {/* ── Loading indicator — single unobtrusive line ─────────────── */}
          {activeTab === "heatmap" && heatmapLoading && selectedSpecies && (
            <div style={{
              position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)",
              display: "flex", alignItems: "center", gap: 6,
              background: "rgba(13,11,8,0.88)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--r-md)",
              padding: "0.35rem 0.75rem",
              zIndex: 20,
            }}>
              <div style={{ width: 8, height: 8, border: "1px solid var(--accent-primary)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.58rem", letterSpacing: "0.08em", color: "var(--text-muted)", textTransform: "uppercase" }}>
                Fetching from GBIF
              </span>
            </div>
          )}

          {/* ── HUD: tabs + year scroller ────────────────────────────────── */}
          <div style={{
            position: "absolute",
            bottom: 20,
            left: "50%",
            transform: "translateX(-50%)",
            width: "min(480px, 90%)",
            zIndex: 10,
            display: "flex",
            flexDirection: "column",
            gap: 6,
          }}>
            {/* Tab toggle */}
            <div style={{
              display: "flex",
              background: "rgba(13,11,8,0.92)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--r-md)",
              overflow: "hidden",
            }}>
              {(["heatmap", "migration"] as const).map(tab => (
                <button key={tab} onClick={() => setActiveTab(tab)}
                  style={{
                    flex: 1,
                    padding: "0.55rem 0",
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.58rem",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: activeTab === tab ? "var(--accent-primary)" : "var(--text-ghost)",
                    background: activeTab === tab ? "rgba(201,130,64,0.08)" : "transparent",
                    border: "none",
                    borderBottom: activeTab === tab ? "1px solid var(--accent-primary)" : "1px solid transparent",
                    cursor: "pointer",
                    transition: "color 140ms ease, background 140ms ease",
                  }}
                >
                  {tab === "heatmap" ? "Heatmap" : "Migration"}
                </button>
              ))}
            </div>

            {/* Year scroller */}
            {activeTab === "heatmap" && (
              <div style={{
                background: "rgba(13,11,8,0.92)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--r-md)",
                padding: "0.6rem 0.75rem",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.4rem" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.53rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-ghost)" }}>Year</span>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
                    {timeline?.timeline && (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", color: "var(--text-ghost)" }}>
                        {(timeline.timeline[year]?.total ?? 0).toLocaleString()} records
                      </span>
                    )}
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", color: "var(--accent-primary)" }}>{year}</span>
                  </div>
                </div>

                <div id="year-scroller" className="scrollbar-hide"
                  style={{ display: "flex", gap: 4, overflowX: "auto", paddingBottom: 2 }}>
                  {years.map(yr => {
                    const isActive = yr === year;
                    const val = timeline?.timeline?.[yr]?.total ?? 0;
                    const barPct = maxTimelineVal > 0 ? (val / maxTimelineVal) * 100 : 0;
                    return (
                      <button
                        key={yr}
                        data-year={yr}
                        onClick={() => setYear(yr)}
                        style={{
                          flexShrink: 0,
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                          gap: 3,
                          padding: "0.35rem 0.5rem",
                          background: isActive ? "rgba(201,130,64,0.1)" : "transparent",
                          border: `1px solid ${isActive ? "rgba(201,130,64,0.3)" : "transparent"}`,
                          borderRadius: "var(--r-sm)",
                          cursor: "pointer",
                          minWidth: 40,
                          transition: "background 120ms ease",
                        }}
                        title={`${yr}: ${val.toLocaleString()} records`}
                      >
                        {/* Mini bar */}
                        <div style={{ width: "100%", height: 10, display: "flex", alignItems: "flex-end" }}>
                          <div style={{
                            width: "100%",
                            height: `${Math.max(15, barPct)}%`,
                            background: isActive ? "var(--accent-primary)"
                              : barPct > 60 ? "rgba(196,151,58,0.5)"
                              : barPct > 30 ? "rgba(122,158,122,0.4)"
                              : "var(--border-strong)",
                            borderRadius: 1,
                            transition: "height 200ms ease",
                          }} />
                        </div>
                        <span style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.5rem",
                          color: isActive ? "var(--accent-primary)" : "var(--text-ghost)",
                        }}>{yr}</span>
                      </button>
                    );
                  })}
                </div>

                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.5rem", color: "var(--text-ghost)", textAlign: "center", marginTop: "0.3rem", letterSpacing: "0.06em" }}>
                  ← → navigate years
                </p>
              </div>
            )}

            {/* Migration controls */}
            {activeTab === "migration" && migrationData?.routes?.length > 0 && (
              <div style={{
                background: "rgba(13,11,8,0.92)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--r-md)",
                padding: "0.6rem 0.75rem",
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
              }}>
                <button onClick={toggleAnimation}
                  style={{
                    width: 28, height: 28, borderRadius: "50%",
                    background: "var(--accent-primary)", border: "none",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    cursor: "pointer", flexShrink: 0,
                  }}>
                  {animating ? <Pause size={11} style={{ color: "#0d0b08", fill: "#0d0b08" }} /> : <Play size={11} style={{ color: "#0d0b08", fill: "#0d0b08", marginLeft: 1 }} />}
                </button>
                <div style={{ flex: 1 }}>
                  <p style={{ fontFamily: "var(--font-serif)", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    {animating ? `Waypoint ${animFrame + 1} / ${migrationData.routes[0]?.waypoints?.length}` : "Animate migration route"}
                  </p>
                  {animWaypoint && (
                    <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.58rem", color: "var(--accent-primary)", letterSpacing: "0.04em" }}>
                      {animWaypoint.location_name}
                    </p>
                  )}
                </div>
                <button onClick={() => { clearInterval(animRef.current); setAnimating(false); setAnimFrame(0); }}
                  style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                  <RotateCcw size={12} style={{ color: "var(--text-ghost)" }} />
                </button>
              </div>
            )}
          </div>

          {/* ── Data density ─────────────────────────────────────────────── */}
          {activeTab === "heatmap" && heatmapData && (
            <div style={{
              position: "absolute", top: 12, right: 12,
              background: "rgba(13,11,8,0.88)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--r-md)",
              padding: "0.4rem 0.65rem",
              zIndex: 10,
            }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", color: "var(--state-warning)" }}>
                {heatmapData.total_records.toLocaleString()}
              </span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", color: "var(--text-ghost)", marginLeft: 4 }}>
                records
                {selectedCountry !== "GLOBAL" && ` · ${COUNTRY_OPTIONS.find(c => c.code === selectedCountry)?.name ?? selectedCountry}`}
              </span>
            </div>
          )}

          {/* ── Heatmap legend ────────────────────────────────────────────── */}
          {activeTab === "heatmap" && heatmapData && heatmapData.total_points > 0 && (
            <div style={{
              position: "absolute", bottom: 20, right: 12,
              background: "rgba(13,11,8,0.88)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--r-md)",
              padding: "0.4rem 0.65rem",
              display: "flex",
              alignItems: "center",
              gap: 6,
              zIndex: 10,
            }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.52rem", color: "var(--text-ghost)", letterSpacing: "0.06em" }}>Low</span>
              <div style={{ width: 80, height: 4, borderRadius: 2, background: "linear-gradient(to right, rgba(180,140,80,0.6), rgba(201,130,64,0.8), rgba(185,78,40,0.9), rgba(148,28,28,1))" }} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.52rem", color: "var(--text-ghost)", letterSpacing: "0.06em" }}>High</span>
            </div>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default function MapsPage() {
  return (
    <Suspense fallback={
      <div style={{ paddingTop: 48, height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-primary)" }}>
        <div style={{ width: 12, height: 12, border: "1px solid var(--accent-primary)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    }>
      <MapsPageInner />
    </Suspense>
  );
}
