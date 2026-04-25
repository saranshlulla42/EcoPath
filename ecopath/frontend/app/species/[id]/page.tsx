"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getGBIFSpeciesDetail, getGBIFOccurrences } from "@/lib/api";
import { ExternalLink, Play, Pause, Loader2, Globe, ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { COUNTRY_OPTIONS } from "@/lib/countries";
import { useMemo, useRef, useState, useEffect } from "react";
import type { PopulationYearSummary } from "@/lib/types";
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  Area, AreaChart, CartesianGrid, ReferenceLine,
} from "recharts";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers — all logic preserved exactly
// ─────────────────────────────────────────────────────────────────────────────

function buildPopulationHistory(occurrences: any[]): PopulationYearSummary[] {
  const yearMap = new Map<number, { count: number; states: Set<string> }>();
  for (const occ of occurrences) {
    const yr = occ.year;
    if (!yr) continue;
    const entry = yearMap.get(yr) ?? { count: 0, states: new Set() };
    entry.count++;
    if (occ.stateProvince) entry.states.add(occ.stateProvince);
    yearMap.set(yr, entry);
  }
  return Array.from(yearMap.entries())
    .sort(([a], [b]) => a - b)
    .map(([year, { count, states }]) => ({
      year,
      total_observations: count,
      states_observed: states.size,
    }));
}

function computeClientAnomalies(history: PopulationYearSummary[]) {
  const sorted = [...history].sort((a, b) => a.year - b.year);
  const results: Array<{
    year: number; type: "surge" | "dip";
    magnitude_pct: number; observed: number; expected: number;
    severity: "low" | "medium" | "high" | "critical";
  }> = [];
  for (let i = 0; i < sorted.length; i++) {
    const cur = sorted[i];
    const prior = sorted.filter(p => p.year >= cur.year - 5 && p.year < cur.year);
    if (prior.length < 2) continue;
    const counts = prior.map(p => p.total_observations);
    const avg = counts.reduce((s, v) => s + v, 0) / counts.length;
    if (avg === 0) continue;
    const variance = counts.reduce((s, v) => s + Math.pow(v - avg, 2), 0) / counts.length;
    const stddev = Math.sqrt(variance);
    const magnitude_pct = ((cur.total_observations - avg) / avg) * 100;
    let flagged = false, z_score = 0;
    if (stddev > 0) { z_score = Math.abs(cur.total_observations - avg) / stddev; flagged = z_score >= 1.5; }
    else { flagged = Math.abs(magnitude_pct) >= 25; z_score = Math.abs(magnitude_pct) / 25; }
    if (!flagged) continue;
    let severity: "low" | "medium" | "high" | "critical";
    if (z_score >= 3.0) severity = "critical";
    else if (z_score >= 2.5) severity = "high";
    else if (z_score >= 2.0) severity = "medium";
    else severity = "low";
    results.push({ year: cur.year, type: magnitude_pct > 0 ? "surge" : "dip",
      magnitude_pct: Math.round(magnitude_pct * 100) / 100,
      observed: cur.total_observations, expected: Math.round(avg), severity });
  }
  return results;
}

async function fetchWikipediaData(scientificName: string) {
  const encoded = encodeURIComponent(scientificName.replace(/ /g, "_"));
  const res = await fetch(`https://en.wikipedia.org/api/rest_v1/page/summary/${encoded}`);
  if (!res.ok) return null;
  const data = await res.json();
  return {
    imageUrl: data.thumbnail?.source ?? null,
    extract: data.extract ? data.extract.split(".").slice(0, 3).join(".") + "." : null,
    pageUrl: data.content_urls?.desktop?.page ?? null,
  };
}

async function fetchGBIFMedia(gbifKey: string) {
  const res = await fetch(`https://api.gbif.org/v1/species/${gbifKey}/media`);
  if (!res.ok) return null;
  const data = await res.json();
  const img = data.results?.find((m: any) => m.type === "StillImage" && m.identifier);
  return img?.identifier ?? null;
}

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

async function fetchXenoCanto(scientificName: string) {
  const tryFetch = async (query: string) => {
    const res = await fetch(`${BACKEND_URL}/api/xenocanto?query=${encodeURIComponent(query)}`);
    if (!res.ok) return null;
    const data = await res.json();
    if (!data.recordings || data.recordings.length === 0) return null;
    const rec = data.recordings[0];
    const audioUrl = `${BACKEND_URL}/api/xenocanto/audio/${rec.id}`;
    return { id: rec.id, audioUrl, recordist: rec.rec, location: rec.loc, country: rec.cnt, type: rec.type, quality: rec.q };
  };
  const quoted = `sp:"${scientificName}"`;
  const indiaResult = await tryFetch(`${quoted} cnt:india`);
  if (indiaResult) return indiaResult;
  return tryFetch(quoted);
}

// ─────────────────────────────────────────────────────────────────────────────
// AudioPlayer — minimal field-notes style
// ─────────────────────────────────────────────────────────────────────────────
function AudioPlayer({ src, type, recordist, country, xcId }: {
  src: string; type?: string; recordist?: string; country?: string; xcId?: string;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [hasError, setHasError] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);

  // Derived: progress 0–100, only meaningful once duration is known
  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  const togglePlay = () => {
    const a = audioRef.current;
    if (!a || hasError) return;
    if (a.paused) {
      a.play().catch(() => setHasError(true));
    } else {
      a.pause();
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const a = audioRef.current;
    if (!a) return;
    const pct = parseFloat(e.target.value);
    // Use live a.duration, not state, to avoid stale closure
    const dur = a.duration;
    if (isFinite(dur) && dur > 0) {
      a.currentTime = (pct / 100) * dur;
      setCurrentTime(a.currentTime);
    }
  };

  const formatTime = (t: number) => isFinite(t) && t >= 0
    ? `${Math.floor(t / 60)}:${Math.floor(t % 60).toString().padStart(2, "0")}`
    : "--:--";

  if (hasError) return (
    <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", color: "var(--danger)", letterSpacing: "0.08em", textTransform: "uppercase", fontWeight: 500 }}>
      Audio unavailable
    </p>
  );

  return (
    <div>
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => { setIsPlaying(false); setCurrentTime(0); }}
        onWaiting={() => setIsBuffering(true)}
        onCanPlay={() => setIsBuffering(false)}
        onTimeUpdate={() => {
          const a = audioRef.current;
          if (!a) return;
          setCurrentTime(a.currentTime);
          if (isFinite(a.duration) && a.duration > 0) setDuration(a.duration);
        }}
        onLoadedMetadata={() => {
          const a = audioRef.current;
          if (!a) return;
          if (isFinite(a.duration) && a.duration > 0) setDuration(a.duration);
        }}
        onError={() => setHasError(true)}
      />

      {/* Controls row */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
        <button
          onClick={togglePlay}
          style={{
            width: 28, height: 28,
            borderRadius: "50%",
            background: "var(--accent-primary)",
            border: "none",
            cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {isBuffering
            ? <Loader2 size={12} style={{ color: "#FFFFFF", animation: "spin 0.7s linear infinite" }} />
            : isPlaying
              ? <Pause size={11} style={{ color: "#FFFFFF", fill: "#FFFFFF" }} />
              : <Play size={11} style={{ color: "#FFFFFF", fill: "#FFFFFF", marginLeft: 1 }} />
          }
        </button>

        <div style={{ flex: 1 }}>
          <input
            type="range" min="0" max="100" step="0.1"
            value={progress}
            onChange={handleSeek}
            style={{ width: "100%", accentColor: "var(--accent-primary)" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", color: "var(--text-muted)" }}>
              {formatTime(currentTime)}
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", color: "var(--text-muted)" }}>
              {formatTime(duration)}
            </span>
          </div>
        </div>
      </div>

      {/* Metadata */}
      <div style={{ display: "flex", alignItems: "baseline", gap: "0.75rem", flexWrap: "wrap" }}>
        {type && <span style={{ fontFamily: "var(--font-serif)", fontSize: "0.75rem", fontStyle: "italic", color: "var(--text-muted)" }}>{type}</span>}
        {recordist && <span style={{ fontFamily: "var(--font-serif)", fontSize: "0.75rem", color: "var(--text-muted)" }}>rec. {recordist}</span>}
        {country && <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", color: "var(--text-ghost)", letterSpacing: "0.06em" }}>{country}</span>}
        {xcId && (
          <a href={`https://xeno-canto.org/${xcId}`} target="_blank" rel="noopener noreferrer"
            style={{ fontFamily: "var(--font-mono)", fontSize: "0.58rem", letterSpacing: "0.06em", color: "var(--text-ghost)", marginLeft: "auto" }}>
            XC{xcId} ↗
          </a>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Ecology Data Component (Cached AI Answers)
// ─────────────────────────────────────────────────────────────────────────────
function EcologyAnswers({ speciesId, commonName, scientificName }: { speciesId: string, commonName: string, scientificName: string }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ecology-data", speciesId],
    queryFn: async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/species/${speciesId}/ecology-data?common_name=${encodeURIComponent(commonName)}&scientific_name=${encodeURIComponent(scientificName)}`);
        if (!res.ok) {
          console.error("FastAPI Error: Ecology data fetch failed with status " + res.status);
          throw new Error("Failed to fetch ecology data");
        }
        return await res.json();
      } catch (err) {
        console.error("Error fetching ecology data:", err);
        throw err;
      }
    },
    enabled: !!speciesId && !!commonName && !!scientificName,
    staleTime: 1000 * 60 * 60, // 1 hour caching on the React side
    retry: 0, // Disable retries to avoid "infinite loading" feeling on 500s
  });

  const [openId, setOpenId] = useState<string | null>(null);

  const QUESTION_MAP: Record<string, string> = {
    taxonomic_identity: "What is the taxonomic identity of the species?",
    geographic_distribution: "What is its geographic distribution and range?",
    diet: "What are its dietary characteristics?",
    predators: "What are its known predators and predation risks?",
    activity_patterns: "What are its activity patterns (diurnal, nocturnal, seasonal)?",
    reproductive_traits: "What are its reproductive traits and lifecycle characteristics?",
    migration: "What are its movement and migration dynamics?",
    habitat: "What are its habitat requirements and ecological niches?",
    threats: "What are the principal threats to the species?",
    population_trends: "What are the trends and drivers of its population dynamics?",
  };

  const keys = Object.keys(QUESTION_MAP);

  if (isLoading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "4rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "3rem" }}>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "1rem", fontWeight: 500 }}>
          Ecological Profile
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {keys.map((k, i) => (
            <motion.div
              key={k}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.1, duration: 0.5 }}
              style={{ height: "3.5rem", background: "var(--surface)", borderRadius: "var(--r-md)" }}
              className="shimmer"
            />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "4rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "3rem" }}>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "0.5rem", fontWeight: 500 }}>
          Ecological Profile
        </p>
        <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-md)", background: "var(--surface-raised)", padding: "1.25rem", boxShadow: "var(--shadow-card)" }}>
          <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.875rem", color: "var(--text-secondary)", fontStyle: "italic" }}>
            Failed to load ecological data.
          </p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "4rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "3rem" }}>
      <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "0.5rem", fontWeight: 500 }}>
        Ecological Profile
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <AnimatePresence>
          {keys.map((key) => {
            const isOpen = openId === key;
            return (
              <motion.div
                key={key}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                style={{
                  border: `1px solid ${isOpen ? "var(--accent-primary)" : "var(--border)"}`,
                  borderRadius: "var(--r-md)",
                  background: "var(--surface-raised)",
                  overflow: "hidden",
                  transition: "border-color 160ms ease",
                  boxShadow: "var(--shadow-card)",
                }}
              >
                <button
                  onClick={() => setOpenId(isOpen ? null : key)}
                  style={{
                    width: "100%", textAlign: "left", padding: "1.15rem 1.25rem",
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    background: "transparent", border: "none", cursor: "pointer",
                    fontFamily: "var(--font-sans)", fontSize: "0.95rem",
                    color: isOpen ? "var(--accent-primary)" : "var(--text-primary)",
                    fontWeight: 500,
                  }}
                >
                  {QUESTION_MAP[key]}
                  <ChevronDown
                    size={16}
                    style={{
                      color: isOpen ? "var(--accent-primary)" : "var(--text-secondary)",
                      transition: "transform 200ms ease", transform: isOpen ? "rotate(180deg)" : "rotate(0deg)"
                    }}
                  />
                </button>
                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25, ease: "easeInOut" }}
                    >
                      <div style={{ padding: "0 1.25rem 1.25rem 1.25rem" }}>
                        <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.9rem", lineHeight: 1.75, color: "var(--text-secondary)" }}>
                          {data[key] || "No information available."}
                        </p>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────────────────────
export default function SpeciesDetailPage() {
  const { id: gbifKey } = useParams<{ id: string }>();
  const router = useRouter();

  const { data: gbifSpecies, isLoading: loadingSpecies } = useQuery({
    queryKey: ["gbif-species", gbifKey],
    queryFn: () => getGBIFSpeciesDetail(gbifKey),
    enabled: !!gbifKey,
  });

  const [selectedCountry, setSelectedCountry] = useState<string>("GLOBAL");
  const selectedCountryName = COUNTRY_OPTIONS.find(c => c.code === selectedCountry)?.name ?? "Global";

  const { data: occurrenceData, isLoading: loadingOcc } = useQuery({
    queryKey: ["gbif-occurrences", gbifKey, selectedCountry],
    queryFn: () => getGBIFOccurrences(gbifKey, selectedCountry),
    enabled: !!gbifKey,
  });

  const scientificName = gbifSpecies?.canonicalName ?? gbifSpecies?.scientificName ?? "";

  const { data: wikiData, isLoading: loadingWiki } = useQuery({
    queryKey: ["wikipedia", scientificName],
    queryFn: () => fetchWikipediaData(scientificName),
    enabled: !!scientificName,
  });

  const { data: gbifMediaUrl } = useQuery({
    queryKey: ["gbif-media-fallback", gbifKey],
    queryFn: () => fetchGBIFMedia(gbifKey),
    enabled: !!gbifKey && wikiData !== undefined && !wikiData?.imageUrl,
  });

  const { data: xenoData } = useQuery({
    queryKey: ["xeno-canto", scientificName],
    queryFn: () => fetchXenoCanto(scientificName),
    enabled: !!scientificName,
  });

  const commonName   = gbifSpecies?.vernacularName ?? gbifSpecies?.canonicalName ?? "Unknown";
  const family       = gbifSpecies?.family ?? "";
  const order        = gbifSpecies?.order ?? "";
  const kingdom      = gbifSpecies?.kingdom ?? "";
  const resolvedImageUrl = wikiData?.imageUrl ?? gbifMediaUrl ?? null;

  const populationHistory = useMemo(() => buildPopulationHistory(occurrenceData?.results ?? []), [occurrenceData]);
  const anomalies = useMemo(() => computeClientAnomalies(populationHistory), [populationHistory]);
  const anomalyYears = new Set(anomalies.map(a => a.year));
  const anomalyMap   = new Map(anomalies.map(a => [a.year, a]));

  const chartData = populationHistory.map(p => ({
    year: p.year,
    count: p.total_observations,
    isAnomaly: anomalyYears.has(p.year),
    anomalyType: anomalyMap.get(p.year)?.type,
  }));

  const totalOccurrences = occurrenceData?.count ?? 0;
  const statesSet = new Set<string>();
  for (const occ of occurrenceData?.results ?? []) {
    if (occ.stateProvince) statesSet.add(occ.stateProvince);
  }

  // ── Loading ──
  if (loadingSpecies) {
    return (
      <div style={{ paddingTop: 52, minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--background)" }}>
        <div style={{ width: 14, height: 14, border: "1.5px solid var(--accent-primary)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!gbifSpecies) {
    return (
      <div style={{ paddingTop: 52, minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--background)" }}>
        <div style={{ textAlign: "center" }}>
          <p style={{ fontFamily: "var(--font-sans)", color: "var(--danger)", marginBottom: "1rem" }}>Species not found on GBIF.</p>
          <button onClick={() => router.back()} style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--accent-primary)", background: "none", border: "none", cursor: "pointer" }}>← Back</button>
        </div>
      </div>
    );
  }

  const taxonomyChips = [kingdom, order, family].filter(Boolean);

  return (
    <div style={{ background: "var(--background)", minHeight: "100vh", paddingTop: 52 }}>
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "3rem 1.5rem 5rem" }}>

        {/* Back */}
        <button
          onClick={() => router.back()}
          style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer", marginBottom: "2.5rem", display: "block", transition: "color 120ms ease", fontWeight: 500 }}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--accent-primary)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--text-tertiary)")}
        >
          ← Back to search
        </button>

        {/* ── Two-column layout ──────────────────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: "3rem", alignItems: "start" }} className="species-grid">

          {/* ── Left column ─────────────────────────────────────────────── */}
          <div>
            {/* Species identity */}
            <h1 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(1.9rem, 4.3vw, 3rem)", fontWeight: 500, color: "var(--text-primary)", lineHeight: 1.1, marginBottom: "0.4rem", letterSpacing: "-0.01em" }}>
              {commonName}
            </h1>
            <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.875rem", fontStyle: "italic", color: "var(--text-secondary)", marginBottom: "1rem" }}>
              {scientificName}
            </p>

            {/* Taxonomy — chips */}
            {taxonomyChips.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "2rem" }}>
                {taxonomyChips.map((t) => (
                  <span key={t} style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.7rem",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: "var(--accent-primary)",
                    background: "var(--accent-muted)",
                    padding: "2px 8px",
                    borderRadius: "var(--r-sm)",
                    fontWeight: 500,
                  }}>
                    {t}
                  </span>
                ))}
              </div>
            )}

            <hr className="field-rule" style={{ marginBottom: "2rem" }} />

            {/* Wikipedia extract */}
            {loadingWiki ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "2rem" }}>
                {[100, 90, 75].map(w => (
                  <div key={w} className="shimmer" style={{ height: 12, width: `${w}%`, background: "var(--surface)", borderRadius: 2 }} />
                ))}
              </div>
            ) : wikiData?.extract && (
              <div style={{ marginBottom: "2rem", maxWidth: 640 }}>
                <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.95rem", lineHeight: 1.75, color: "var(--text-primary)", marginBottom: "0.6rem" }}>
                  {wikiData.extract}
                </p>
                {wikiData.pageUrl && (
                  <a href={wikiData.pageUrl} target="_blank" rel="noopener noreferrer"
                    style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.12em", color: "var(--accent-primary)", textTransform: "uppercase", fontWeight: 500 }}>
                    Wikipedia ↗
                  </a>
                )}
              </div>
            )}

            {/* Region selector */}
            <div style={{ marginBottom: "2rem" }}>
              <label style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", display: "block", marginBottom: "0.5rem", fontWeight: 500 }}>
                Region
              </label>
              <div style={{ position: "relative", display: "inline-block" }}>
                <Globe size={14} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-tertiary)", pointerEvents: "none" }} />
                <select
                  value={selectedCountry}
                  onChange={e => setSelectedCountry(e.target.value)}
                  style={{
                    background: "var(--surface-raised)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--r-lg)",
                    color: "var(--text-primary)",
                    fontFamily: "var(--font-sans)",
                    fontSize: "0.875rem",
                    paddingLeft: "2rem",
                    paddingRight: "1rem",
                    paddingTop: "0.5rem",
                    paddingBottom: "0.5rem",
                    outline: "none",
                    cursor: "pointer",
                    appearance: "none",
                    minWidth: 200,
                  }}
                >
                  {COUNTRY_OPTIONS.map(opt => (
                    <option key={opt.code} value={opt.code}>{opt.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Stats — inline row */}
            <div style={{ display: "flex", gap: "2.5rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
              {[
                { value: loadingOcc ? "—" : totalOccurrences.toLocaleString(), label: `Occurrences · ${selectedCountry === "GLOBAL" ? "Global" : selectedCountryName}` },
                { value: loadingOcc ? "—" : statesSet.size, label: "Regions observed" },
                { value: loadingOcc ? "—" : populationHistory.length, label: "Years with data" },
              ].map(({ value, label }) => (
                <div key={label}>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "1.55rem", color: "var(--text-primary)", lineHeight: 1, marginBottom: "0.3rem", fontWeight: 600 }}>
                    {value}
                  </p>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.7rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-tertiary)", fontWeight: 500 }}>
                    {label}
                  </p>
                </div>
              ))}
            </div>

            {/* Regions */}
            {statesSet.size > 0 && (
              <div style={{ marginBottom: "2rem" }}>
                <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.8 }}>
                  {[...statesSet].sort().join(" · ")}
                </p>
              </div>
            )}

            <hr className="field-rule" style={{ marginBottom: "1.5rem" }} />

            {/* Action links */}
            <div style={{ display: "flex", gap: "2rem", alignItems: "center" }}>
              <button
                onClick={() => router.push(`/maps?species=${gbifKey}`)}
                style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--accent-primary)", background: "none", border: "none", cursor: "pointer", padding: 0, fontWeight: 500 }}
                onMouseEnter={e => (e.currentTarget.style.textDecoration = "underline")}
                onMouseLeave={e => (e.currentTarget.style.textDecoration = "none")}
              >
                View on map →
              </button>
              <button
                onClick={() => router.push(`/chat?species=${gbifKey}`)}
                style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--accent-primary)", background: "none", border: "none", cursor: "pointer", padding: 0, fontWeight: 500 }}
                onMouseEnter={e => (e.currentTarget.style.textDecoration = "underline")}
                onMouseLeave={e => (e.currentTarget.style.textDecoration = "none")}
              >
                Ask EcoPath →
              </button>
              <a href={`https://www.gbif.org/species/${gbifKey}`} target="_blank" rel="noopener noreferrer"
                style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--accent-primary)", marginLeft: "auto", fontWeight: 500 }}
                onMouseEnter={e => (e.currentTarget.style.textDecoration = "underline")}
                onMouseLeave={e => (e.currentTarget.style.textDecoration = "none")}
              >
                GBIF ↗
              </a>
            </div>
          </div>

          {/* ── Right column ─────────────────────────────────────────────── */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            {/* Image */}
            <div style={{ aspectRatio: "1 / 1", overflow: "hidden", borderRadius: "var(--r-lg)", background: "var(--surface)", border: "1px solid var(--border)" }}>
              {loadingWiki ? (
                <div className="shimmer" style={{ width: "100%", height: "100%", background: "var(--surface-raised)" }} />
              ) : resolvedImageUrl ? (
                <img src={resolvedImageUrl} alt={commonName} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", color: "var(--text-tertiary)", letterSpacing: "0.12em", textTransform: "uppercase", fontWeight: 500 }}>No image</p>
                </div>
              )}
            </div>

            {/* Audio */}
            {xenoData && (
              <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "1rem" }}>
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "0.75rem", fontWeight: 500 }}>
                  Field Recording
                </p>
                <AudioPlayer
                  src={xenoData.audioUrl}
                  type={xenoData.type}
                  recordist={xenoData.recordist}
                  country={xenoData.country}
                  xcId={xenoData.id}
                />
              </div>
            )}
          </div>
        </div>

        {/* ── Population trend ──────────────────────────────────────────── */}
        {chartData.length > 0 && (
          <div style={{ marginTop: "4rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "3rem" }}>
            <div style={{ marginBottom: "1.5rem" }}>
              <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "0.4rem", fontWeight: 500 }}>
                Population Trend
              </p>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
                <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.85rem", fontStyle: "italic", color: "var(--text-secondary)" }}>
                  GBIF occurrence records by year · {selectedCountry === "GLOBAL" ? "Global" : selectedCountryName} · anomalies at &gt;1.5 std dev
                </p>
                {anomalies.length > 0 && (
                  <div style={{ display: "flex", gap: "0.75rem" }}>
                    {anomalies.slice(0, 3).map(a => (
                      <span key={a.year} style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.62rem",
                        letterSpacing: "0.08em",
                        color: a.type === "dip" ? "var(--danger)" : "var(--warning)",
                        fontWeight: 500,
                      }}>
                        {a.year} {a.type === "dip" ? "▼" : "▲"}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={chartData} margin={{ top: 8, right: 0, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#5BB89A" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#5BB89A" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 4" stroke="rgba(74,103,65,0.08)" />
                <XAxis dataKey="year" tick={{ fill: "var(--text-tertiary)", fontSize: 10, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "var(--text-tertiary)", fontSize: 10, fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text-primary)", fontFamily: "var(--font-sans)", fontSize: 13, boxShadow: "var(--shadow-card)" }}
                  labelStyle={{ color: "var(--text-tertiary)", fontFamily: "var(--font-mono)", fontSize: 10, marginBottom: 2, letterSpacing: "0.08em", textTransform: "uppercase" }}
                />
                {[...anomalyYears].map(yr => {
                  const anom = anomalyMap.get(yr);
                  const isDip = anom?.type === "dip";
                  return (
                    <ReferenceLine key={yr} x={yr}
                      stroke={isDip ? "var(--danger)" : "var(--warning)"}
                      strokeDasharray="2 3" strokeOpacity={0.55}
                      label={{ value: isDip ? "▼" : "▲", position: "top", fill: isDip ? "var(--danger)" : "var(--warning)", fontSize: 9 }}
                    />
                  );
                })}
                <Area type="monotone" dataKey="count" stroke="var(--accent-data)" strokeWidth={1.75}
                  fill="url(#areaGrad)"
                  dot={(props: any) => {
                    const { cx, cy, payload } = props;
                    if (payload.isAnomaly) {
                      const isDip = payload.anomalyType === "dip";
                      return <circle key={payload.year} cx={cx} cy={cy} r={4} fill={isDip ? "var(--danger)" : "var(--warning)"} stroke="var(--background)" strokeWidth={1.5} />;
                    }
                    return <circle key={payload.year} cx={cx} cy={cy} r={2.5} fill="var(--accent-data)" opacity={0.7} />;
                  }}
                  activeDot={{ r: 5, fill: "var(--accent-primary)" }} name="Observations"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* ── Anomaly report ─────────────────────────────────────────────── */}
        {anomalies.length > 0 && (
          <div style={{ marginTop: "3.5rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "2.5rem" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "0.4rem", fontWeight: 500 }}>
              Anomaly Record
            </p>
            <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.85rem", fontStyle: "italic", color: "var(--text-secondary)", marginBottom: "2rem" }}>
              {anomalies.length} event{anomalies.length !== 1 ? "s" : ""} flagged at &gt;1.5 std dev from 5-year rolling average
              — {anomalies.filter(a => a.type === "dip").length} dip{anomalies.filter(a => a.type === "dip").length !== 1 ? "s" : ""}
              , {anomalies.filter(a => a.type === "surge").length} surge{anomalies.filter(a => a.type === "surge").length !== 1 ? "s" : ""}
            </p>

            {anomalies.map((a, i) => {
              const isDip = a.type === "dip";
              return (
                <div key={a.year} style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "1.5rem",
                  padding: "1.25rem 0",
                  borderTop: i > 0 ? "1px solid var(--border-subtle)" : "none",
                }}>
                  {/* Year + type */}
                  <div style={{ minWidth: 72 }}>
                    <p style={{ fontFamily: "var(--font-mono)", fontSize: "1rem", color: isDip ? "var(--danger)" : "var(--warning)", lineHeight: 1, fontWeight: 600 }}>
                      {a.year}
                    </p>
                    <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-tertiary)", marginTop: 4, fontWeight: 500 }}>
                      {a.type}
                    </p>
                  </div>

                  {/* Detail */}
                  <div style={{ flex: 1 }}>
                    <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.875rem", color: "var(--text-primary)", marginBottom: "0.4rem", lineHeight: 1.5 }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", color: isDip ? "var(--danger)" : "var(--warning)", fontWeight: 600 }}>
                        {a.magnitude_pct > 0 ? "+" : ""}{a.magnitude_pct.toFixed(0)}%
                      </span>
                      {" "}vs 5-yr avg · observed {a.observed.toLocaleString()} vs expected {a.expected.toLocaleString()}
                    </p>
                    <span style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.6rem",
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      fontWeight: 500,
                      color: a.severity === "critical" ? "var(--danger)"
                           : a.severity === "high" ? "var(--warning)"
                           : "var(--text-tertiary)",
                    }}>
                      {a.severity}
                    </span>
                  </div>

                  {/* Investigate */}
                  <button
                    onClick={() => router.push(`/chat?species=${gbifKey}&year=${a.year}`)}
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.62rem",
                      letterSpacing: "0.12em",
                      textTransform: "uppercase",
                      color: "var(--accent-primary)",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      flexShrink: 0,
                      padding: 0,
                      fontWeight: 500,
                    }}
                    onMouseEnter={e => (e.currentTarget.style.textDecoration = "underline")}
                    onMouseLeave={e => (e.currentTarget.style.textDecoration = "none")}
                  >
                    Investigate →
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* ── Ecological Profile (Cached AI Answers) ────────────────────── */}
        <EcologyAnswers speciesId={gbifKey} commonName={commonName} scientificName={scientificName} />

      </div>

      {/* Responsive grid override */}
      <style>{`
        @media (max-width: 700px) {
          .species-grid { grid-template-columns: 1fr !important; }
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.7; } }
      `}</style>
    </div>
  );
}
