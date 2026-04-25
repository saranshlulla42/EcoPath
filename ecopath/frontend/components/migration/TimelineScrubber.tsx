"use client";

import { Play, Pause } from "lucide-react";
import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** Map month index (0–11) to the first ISO week of that month (approximate) */
const MONTH_WEEK_STARTS = [1, 5, 9, 14, 18, 22, 27, 31, 35, 40, 44, 48];

export interface SeasonWindow {
  breeding: [number, number] | null;
  migration: [number, number][];
  wintering: [number, number] | null;
}

interface TimelineScrubberProps {
  currentWeek: number;
  isPlaying: boolean;
  onWeekChange: (week: number) => void;
  onPlayToggle: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  onReset?: () => void;
  /** Season windows computed from observation data */
  seasonWindows?: SeasonWindow | null;
  /** Species dot colour for the wintering band */
  speciesColor?: string;
  dates?: { week: number; label: string }[];
}

export function TimelineScrubber({
  currentWeek,
  isPlaying,
  onWeekChange,
  onPlayToggle,
  onPrev,
  onNext,
  onReset,
  seasonWindows,
  speciesColor = "#06b6d4",
  dates,
}: TimelineScrubberProps) {
  // Determine which month the current week falls in
  let currentMonthIdx = 0;
  for (let i = MONTH_WEEK_STARTS.length - 1; i >= 0; i--) {
    if (currentWeek >= MONTH_WEEK_STARTS[i]) {
      currentMonthIdx = i;
      break;
    }
  }

  // Convert week range to percentage positions on the 1–52 track
  const weekToPercent = (w: number) => ((w - 1) / 51) * 100;

  const bands: { left: number; width: number; color: string; label: string; labelColor: string }[] = [];

  if (seasonWindows) {
    if (seasonWindows.breeding) {
      const [s, e] = seasonWindows.breeding;
      const left = weekToPercent(s);
      const width = weekToPercent(e) - left;
      bands.push({
        left,
        width: Math.max(width, 1),
        color: "rgba(91, 184, 154, 0.22)",
        label: e - s + 1 >= 3 ? "breeding" : "",
        labelColor: "rgba(168, 200, 168, 0.7)",
      });
    }
    for (const [s, e] of seasonWindows.migration) {
      const left = weekToPercent(s);
      const width = weekToPercent(e) - left;
      bands.push({
        left,
        width: Math.max(width, 1),
        color: "rgba(212, 136, 10, 0.22)",
        label: e - s + 1 >= 3 ? "migration" : "",
        labelColor: "rgba(212, 136, 10, 0.75)",
      });
    }
    if (seasonWindows.wintering) {
      const [s, e] = seasonWindows.wintering;
      const left = weekToPercent(s);
      const width = weekToPercent(e) - left;
      bands.push({
        left,
        width: Math.max(width, 1),
        color: `${speciesColor}26`,
        label: e - s + 1 >= 3 ? "wintering" : "",
        labelColor: `${speciesColor}B3`,
      });
    }
  }

  const C_BG     = "var(--map-chrome)";
  const C_BORDER = "var(--map-chrome-border)";
  const C_TEXT   = "var(--map-chrome-text)";
  const C_TEXT3  = "var(--map-chrome-text-3)";
  const C_DATA   = "var(--accent-data)";

  return (
    <div
      id="timeline-scrubber"
      className="migration-controls"
      style={{
        width: "100%",
        background: C_BG,
        borderTop: `1px solid ${C_BORDER}`,
        borderRadius: "0",
        padding: "10px 14px",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
        color: C_TEXT,
        pointerEvents: "auto",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          flexWrap: "wrap",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.35rem",
            flexShrink: 0,
          }}
        >
          <button
            onClick={onPlayToggle}
            id="play-pause-btn"
            aria-label={isPlaying ? "Pause animation" : "Play animation"}
            className="play-btn"
            style={{
              width: 34,
              height: 34,
              borderRadius: "50%",
              background: C_DATA,
              border: "none",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
              color: "var(--map-chrome)",
              flexShrink: 0,
              transition: "background 140ms ease",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--accent-secondary)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = C_DATA)}
          >
            {isPlaying ? (
              <Pause size={13} style={{ fill: "var(--map-chrome)" }} />
            ) : (
              <Play size={13} style={{ fill: "var(--map-chrome)", marginLeft: 1 }} />
            )}
          </button>

          {onPrev && (
            <button
              onClick={onPrev}
              aria-label="Previous frame"
              className="frame-nav-btn"
              style={{
                width: 30,
                height: 30,
                borderRadius: "var(--r-md)",
                background: "transparent",
                border: `1px solid ${C_BORDER}`,
                color: C_TEXT,
                cursor: "pointer",
                display: "grid",
                placeItems: "center",
              }}
            >
              <ChevronLeft size={16} />
            </button>
          )}

          {onNext && (
            <button
              onClick={onNext}
              aria-label="Next frame"
              className="frame-nav-btn"
              style={{
                width: 30,
                height: 30,
                borderRadius: "var(--r-md)",
                background: "transparent",
                border: `1px solid ${C_BORDER}`,
                color: C_TEXT,
                cursor: "pointer",
                display: "grid",
                placeItems: "center",
              }}
            >
              <ChevronRight size={16} />
            </button>
          )}

          {onReset && (
            <button
              onClick={onReset}
              aria-label="Reset animation"
              className="frame-nav-btn"
              style={{
                width: 30,
                height: 30,
                borderRadius: "var(--r-md)",
                background: "transparent",
                border: `1px solid ${C_BORDER}`,
                color: C_TEXT,
                cursor: "pointer",
                display: "grid",
                placeItems: "center",
              }}
            >
              <RotateCcw size={14} />
            </button>
          )}
        </div>

        <div style={{ flex: 1, minWidth: 180 }} />

        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.72rem",
            color: C_DATA,
            minWidth: 38,
            textAlign: "right",
            flexShrink: 0,
            fontWeight: 500,
          }}
        >
          W{String(currentWeek).padStart(2, "0")}
        </span>

        {dates?.length ? (
          <select
            aria-label="Jump to migration date"
            value={currentWeek}
            onChange={(e) => onWeekChange(parseInt(e.target.value, 10))}
            style={{
              background: "var(--map-chrome-input)",
              color: C_TEXT,
              border: `1px solid ${C_BORDER}`,
              borderRadius: "var(--r-md)",
              padding: "0.4rem 0.6rem",
              fontFamily: "var(--font-mono)",
              fontSize: "0.65rem",
              maxWidth: 190,
            }}
          >
            {dates.map((date) => (
              <option key={`${date.week}-${date.label}`} value={date.week}>
                {date.label}
              </option>
            ))}
          </select>
        ) : null}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <div style={{ flex: 1, position: "relative" }}>
          {bands.length > 0 && (
            <div
              style={{
                position: "absolute",
                top: -2,
                left: 0,
                right: 0,
                height: "calc(100% + 4px)",
                pointerEvents: "none",
                zIndex: 0,
              }}
            >
              {bands.map((band, i) => (
                <div key={i}>
                  {/* Band strip */}
                  <div
                    style={{
                      position: "absolute",
                      left: `${band.left}%`,
                      width: `${band.width}%`,
                      top: 0,
                      bottom: 0,
                      background: band.color,
                      borderRadius: 2,
                    }}
                  />
                  {/* Band label */}
                  {band.label && (
                    <span
                      style={{
                        position: "absolute",
                        left: `${band.left + band.width / 2}%`,
                        top: -12,
                        transform: "translateX(-50%)",
                        fontFamily: "var(--font-mono)",
                        fontSize: "9px",
                        color: band.labelColor,
                        whiteSpace: "nowrap",
                        pointerEvents: "none",
                      }}
                    >
                      {band.label}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          <input
            type="range"
            min={1}
            max={52}
            step={1}
            value={currentWeek}
            onChange={(e) => onWeekChange(parseInt(e.target.value, 10))}
            id="week-slider"
            aria-label="Migration week"
            style={{
              flex: 1,
              width: "100%",
              height: 4,
              accentColor: "var(--accent-data)",
              position: "relative",
              zIndex: 1,
              background: `linear-gradient(to right, rgba(91, 184, 154, 0.55) 0%, rgba(91, 184, 154, 0.55) ${weekToPercent(currentWeek)}%, rgba(168, 200, 168, 0.18) ${weekToPercent(currentWeek)}%, rgba(168, 200, 168, 0.18) 100%)`,
            }}
          />
        </div>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 4,
          overflowX: "auto",
          scrollbarWidth: "none",
        }}
      >
        {MONTH_LABELS.map((label, i) => (
          <button
            key={label}
            onClick={() => onWeekChange(MONTH_WEEK_STARTS[i])}
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.55rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: i === currentMonthIdx ? "var(--accent-data)" : C_TEXT3,
              background: i === currentMonthIdx ? "rgba(91, 184, 154, 0.2)" : "none",
              border: "none",
              cursor: "pointer",
              padding: "2px 4px",
              borderRadius: "var(--r-sm)",
              transition: "color 120ms ease, background 120ms ease",
              fontWeight: i === currentMonthIdx ? 500 : 400,
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
