"use client";

import { useState, useMemo } from "react";
import type { MigrationSpeciesInfo } from "@/lib/types";

// ── Species palette — distinctive, ecology-themed ──────────────────────────
const SPECIES_COLORS = [
  "#5BB89A", // accent-data teal
  "#3A9E7A", // accent-secondary
  "#2D7D52", // accent-primary
  "#D4880A", // warning amber
  "#C0392B", // danger
  "#6B8FB8", // dusty blue
  "#A8714A", // earth brown
  "#8B5CA8", // dusty violet
];

const IUCN_BADGE_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  LC: { bg: "rgba(91, 184, 154, 0.2)", color: "#E8F0E6", label: "Least Concern" },
  NT: { bg: "rgba(212, 136, 10, 0.2)",  color: "#E8D8B0", label: "Near Threatened" },
  VU: { bg: "rgba(192, 57, 43, 0.2)",   color: "#F0C8C0", label: "Vulnerable" },
  EN: { bg: "rgba(192, 57, 43, 0.25)",  color: "#F0C8C0", label: "Endangered" },
  CR: { bg: "rgba(192, 57, 43, 0.3)",   color: "#F5D8D0", label: "Critically Endangered" },
  DD: { bg: "rgba(168, 200, 168, 0.15)",color: "#A8C8A8", label: "Data Deficient" },
  NE: { bg: "rgba(168, 200, 168, 0.15)",color: "#A8C8A8", label: "Not Evaluated" },
};

interface SpeciesPanelProps {
  speciesList: MigrationSpeciesInfo[];
  selectedSpeciesCode: string;
  onSelectSpecies: (speciesCode: string) => void;
  isLoading?: boolean;
  /** Gemini-generated migration narrative */
  narrative?: string | null;
  /** Whether the narrative is loading */
  narrativeLoading?: boolean;
  /** IUCN Red List category code (e.g. "LC", "VU") */
  iucnStatus?: string | null;
}

export function SpeciesPanel({
  speciesList,
  selectedSpeciesCode,
  onSelectSpecies,
  isLoading = false,
  narrative = null,
  narrativeLoading = false,
  iucnStatus = null,
}: SpeciesPanelProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const selected = speciesList.find(
    (s) => s.speciesCode === selectedSpeciesCode
  );

  const filteredSpecies = useMemo(() => {
    if (!searchQuery.trim()) {
      return [...speciesList]
        .sort((a, b) => a.commonName.localeCompare(b.commonName))
        .slice(0, 50);
    }
    const lower = searchQuery.toLowerCase();
    return speciesList
      .filter(
        (s) =>
          s.commonName.toLowerCase().includes(lower) ||
          s.scientificName.toLowerCase().includes(lower)
      )
      .slice(0, 50);
  }, [speciesList, searchQuery]);

  const monthNames = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];

  const iucnBadge = iucnStatus ? IUCN_BADGE_STYLES[iucnStatus] : null;

  // Map-chrome palette — dark panel sitting on top of map canvas
  const C_BG     = "var(--map-chrome)";
  const C_BORDER = "var(--map-chrome-border)";
  const C_TEXT   = "var(--map-chrome-text)";
  const C_TEXT2  = "var(--map-chrome-text-2)";
  const C_TEXT3  = "var(--map-chrome-text-3)";
  const C_INPUT  = "var(--map-chrome-input)";
  const C_ACTIVE = "var(--map-chrome-active)";
  const C_DATA   = "var(--accent-data)";

  return (
    <div
      style={{
        width: 260,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        background: C_BG,
        borderRight: `1px solid ${C_BORDER}`,
        overflowY: "auto",
        zIndex: 10,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "1rem",
          borderBottom: `1px solid ${C_BORDER}`,
        }}
      >
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.58rem",
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: C_TEXT3,
            marginBottom: "0.4rem",
            fontWeight: 500,
          }}
        >
          Migration Species
        </p>
        <p
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "0.75rem",
            color: C_TEXT2,
            fontStyle: "italic",
          }}
        >
          {speciesList.length} species tracked
        </p>
        <div style={{ marginTop: "0.75rem", position: "relative" }}>
          <input
            type="text"
            placeholder="Search species..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: "100%",
              padding: "0.5rem 0.7rem",
              background: C_INPUT,
              border: `1px solid ${C_BORDER}`,
              borderRadius: "var(--r-md)",
              fontFamily: "var(--font-sans)",
              fontSize: "0.8rem",
              color: C_TEXT,
              outline: "none",
            }}
          />
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div
          style={{
            padding: "2rem 1rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
          }}
        >
          <div
            style={{
              width: 10,
              height: 10,
              border: `1px solid ${C_DATA}`,
              borderTopColor: "transparent",
              borderRadius: "50%",
              animation: "spin 0.7s linear infinite",
            }}
          />
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.6rem",
              color: C_TEXT3,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontWeight: 500,
            }}
          >
            Loading species
          </span>
        </div>
      )}

      {/* Species list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {filteredSpecies.map((species, i) => {
          const isActive = species.speciesCode === selectedSpeciesCode;
          const color = SPECIES_COLORS[i % SPECIES_COLORS.length];

          return (
            <button
              key={species.speciesCode}
              onClick={() => onSelectSpecies(species.speciesCode)}
              id={`species-${species.speciesCode}`}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "flex-start",
                gap: "0.6rem",
                padding: "0.7rem 1rem",
                background: isActive ? C_ACTIVE : "transparent",
                border: "none",
                borderBottom: `1px solid ${C_BORDER}`,
                borderLeft: isActive
                  ? `2px solid ${C_DATA}`
                  : "2px solid transparent",
                cursor: "pointer",
                textAlign: "left",
                transition: "background 120ms ease, border-color 120ms ease",
              }}
              onMouseEnter={(e) => {
                if (!isActive)
                  e.currentTarget.style.background = "rgba(91, 184, 154, 0.08)";
              }}
              onMouseLeave={(e) => {
                if (!isActive)
                  e.currentTarget.style.background = "transparent";
              }}
            >
              {/* Color dot */}
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: color,
                  flexShrink: 0,
                  marginTop: 5,
                }}
              />

              <div>
                <p
                  style={{
                    fontFamily: "var(--font-sans)",
                    fontSize: "0.8rem",
                    color: isActive ? C_TEXT : "rgba(232, 240, 230, 0.78)",
                    lineHeight: 1.25,
                    marginBottom: 2,
                    fontWeight: isActive ? 500 : 400,
                  }}
                >
                  {species.commonName}
                </p>
                <p
                  style={{
                    fontFamily: "var(--font-sans)",
                    fontSize: "0.7rem",
                    fontStyle: "italic",
                    color: C_TEXT3,
                    lineHeight: 1.2,
                  }}
                >
                  {species.scientificName}
                </p>
              </div>
            </button>
          );
        })}
      </div>

      {/* Info card for selected species */}
      {selected && (
        <div
          style={{
            borderTop: `1px solid ${C_BORDER}`,
            padding: "1rem",
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.58rem",
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: C_TEXT3,
              marginBottom: "0.6rem",
              fontWeight: 500,
            }}
          >
            Species Detail
          </p>

          <p
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "1.1rem",
              fontWeight: 500,
              color: C_TEXT,
              lineHeight: 1.15,
              marginBottom: "0.15rem",
              letterSpacing: "-0.005em",
            }}
          >
            {selected.commonName}
          </p>
          <p
            style={{
              fontFamily: "var(--font-sans)",
              fontSize: "0.72rem",
              fontStyle: "italic",
              color: C_TEXT3,
              marginBottom: "0.4rem",
            }}
          >
            {selected.scientificName}
          </p>

          {/* IUCN Badge */}
          {iucnBadge && (
            <div style={{ marginBottom: "0.6rem" }}>
              <span
                style={{
                  display: "inline-block",
                  fontSize: "0.6rem",
                  fontFamily: "var(--font-mono)",
                  letterSpacing: "0.08em",
                  padding: "2px 7px",
                  borderRadius: "var(--r-sm)",
                  background: iucnBadge.bg,
                  color: iucnBadge.color,
                  fontWeight: 600,
                  textTransform: "uppercase",
                }}
              >
                {iucnBadge.label}
              </span>
            </div>
          )}

          {/* Stats */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem",
            }}
          >
            {selected.totalDistanceKm != null && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.58rem",
                    color: C_TEXT3,
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                    fontWeight: 500,
                  }}
                >
                  Distance
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.85rem",
                    color: C_DATA,
                    fontWeight: 600,
                  }}
                >
                  {selected.totalDistanceKm.toLocaleString()} km
                </span>
              </div>
            )}

            {selected.originRegion && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.58rem",
                    color: C_TEXT3,
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                    fontWeight: 500,
                  }}
                >
                  Origin
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-sans)",
                    fontSize: "0.7rem",
                    color: C_TEXT2,
                  }}
                >
                  {selected.originRegion}
                </span>
              </div>
            )}

            {selected.destinationRegion && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.58rem",
                    color: C_TEXT3,
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                    fontWeight: 500,
                  }}
                >
                  Destination
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-sans)",
                    fontSize: "0.7rem",
                    color: C_TEXT2,
                  }}
                >
                  {selected.destinationRegion}
                </span>
              </div>
            )}

            {selected.activeMonths && selected.activeMonths.length > 0 && (
              <div>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.58rem",
                    color: C_TEXT3,
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                    display: "block",
                    marginBottom: "0.3rem",
                    fontWeight: 500,
                  }}
                >
                  Active months
                </span>
                <div
                  style={{
                    display: "flex",
                    gap: 2,
                  }}
                >
                  {Array.from({ length: 12 }, (_, i) => {
                    const active = selected.activeMonths!.includes(i + 1);
                    return (
                      <div
                        key={i}
                        title={monthNames[i]}
                        style={{
                          flex: 1,
                          height: 4,
                          borderRadius: 1,
                          background: active ? C_DATA : C_BORDER,
                          opacity: active ? 1 : 0.5,
                          transition: "opacity 120ms ease",
                        }}
                      />
                    );
                  })}
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginTop: 3,
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.5rem",
                      color: C_TEXT3,
                    }}
                  >
                    Jan
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.5rem",
                      color: C_TEXT3,
                    }}
                  >
                    Dec
                  </span>
                </div>
              </div>
            )}

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginTop: "0.25rem",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.58rem",
                  color: C_TEXT3,
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  fontWeight: 500,
                }}
              >
                Source
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.62rem",
                  color: C_DATA,
                  letterSpacing: "0.06em",
                  fontWeight: 500,
                }}
              >
                {selected.dataSource === "both"
                  ? "eBird + Movebank"
                  : selected.dataSource === "ebird"
                  ? "eBird"
                  : "Movebank"}
              </span>
            </div>
          </div>

          {/* ── Migration Insights (Gemini narrative) ── */}
          <div style={{ marginTop: "0.9rem", borderTop: `1px solid ${C_BORDER}`, paddingTop: "0.75rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: "0.4rem" }}>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.58rem",
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                  color: C_TEXT3,
                  fontWeight: 500,
                }}
              >
                Migration Insights
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  color: C_TEXT3,
                  opacity: 0.7,
                }}
              >
                via Gemini
              </span>
            </div>

            {narrativeLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {[1, 2, 3].map((n) => (
                  <div
                    key={n}
                    className="shimmer"
                    style={{
                      height: 10,
                      borderRadius: 3,
                      background: C_BORDER,
                      width: n === 3 ? "60%" : "100%",
                    }}
                  />
                ))}
              </div>
            )}

            {!narrativeLoading && narrative && (
              <p
                className="narrative-fade"
                style={{
                  fontFamily: "var(--font-sans)",
                  fontSize: "0.72rem",
                  lineHeight: 1.6,
                  color: C_TEXT2,
                }}
              >
                {narrative}
              </p>
            )}

            {!narrativeLoading && !narrative && (
              <p
                style={{
                  fontFamily: "var(--font-sans)",
                  fontSize: "0.7rem",
                  color: C_TEXT3,
                  fontStyle: "italic",
                }}
              >
                Narrative unavailable for this species.
              </p>
            )}
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
