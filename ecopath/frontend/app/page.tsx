"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { searchSpecies } from "@/lib/api";
import { getResolver } from "@/lib/taxonomy/load";
import type { Resolver } from "@/lib/taxonomy/resolver";
import { parse, type ParseResult } from "@/lib/commands/parse";
import { execute } from "@/lib/commands/execute";
import { COMMANDS } from "@/lib/commands/registry";
import { evidenceLine, statusLabel } from "@/lib/commands/status";
import * as telemetry from "@/lib/commands/telemetry";

/** Indian states the parser recognises as a region argument. */
const REGIONS = new Set([
  "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa",
  "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala",
  "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland",
  "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura",
  "uttar pradesh", "uttarakhand", "west bengal", "delhi", "ladakh",
]);
import { identifyBird } from "@/lib/dataClient";
import type { GBIFSearchResult } from "@/lib/types";


const CAPABILITIES = [
  { index: "I",    label: "Occurrence heatmaps",       detail: "10-year population density maps, 2014–2024",        href: "/maps" },
  { index: "II",   label: "Migration corridors",       detail: "Animated flyway visualizations across major routes", href: "/migration" },
  { index: "III",  label: "Anomaly detection",         detail: "Statistical forensics on population dips and surges", href: null },
  { index: "IV",   label: "Species intelligence",      detail: "Deep profiles, IUCN status, habitat, bird calls",    href: null },
  { index: "V",    label: "AI vision identification",  detail: "Photograph any bird → instant Gemini identification", href: null },
  { index: "VI",   label: "Causal reasoning agent",    detail: "Ask why populations change — grounded RAG responses", href: "/chat" },
];

export default function LandingPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GBIFSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [visionLoading, setVisionLoading] = useState(false);
  const [visionStatus, setVisionStatus] = useState<string | null>(null);
  const [visionError, setVisionError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const uploadRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | undefined>(undefined);
  const [uploadMargin, setUploadMargin] = useState(false);

  const handleSearch = (val: string) => {
    setQuery(val);
    clearTimeout(debounceRef.current);
    if (val.length < 2) { setResults([]); return; }
    debounceRef.current = setTimeout(async () => {
      try {
        setLoading(true);
        const data = await searchSpecies(val);
        setResults(data);
      } catch { setResults([]); }
      finally { setLoading(false); }
    }, 300);
  };

  // ── Command bar ──────────────────────────────────────────────────────────
  // This input is the command centre, not just a species search: the parser
  // runs first and only genuinely open questions reach the agent.
  const [resolver, setResolver] = useState<Resolver | null>(null);
  const [parsed, setParsed] = useState<ParseResult | null>(null);
  const [commandResult, setCommandResult] = useState<React.ReactNode>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    telemetry.load();
    getResolver().then(setResolver).catch(() => setResolver(null));
  }, []);

  useEffect(() => {
    if (!resolver || !query.trim()) { setParsed(null); return; }
    setParsed(parse(query, { resolver, regions: REGIONS }));
  }, [query, resolver]);

  const runCommand = async (text: string) => {
    if (!resolver || !text.trim()) return;
    const t0 = performance.now();
    const result = parse(text, { resolver, regions: REGIONS });
    const parseMs = performance.now() - t0;

    setRunning(true);
    const exec = await execute(result);
    setRunning(false);

    telemetry.record({
      input: text,
      outcome:
        result.kind === "command" ? "command"
        : result.kind === "disambiguate" ? "disambiguate"
        : result.kind === "fallback" ? "fallback"
        : "empty",
      verb: result.kind === "command" ? result.spec.verb : null,
      llmCalled: exec.llmCalled,
      networkCalled: exec.networkCalled,
      parseMs,
      totalMs: performance.now() - t0,
    });

    const a = exec.action;
    if (a.kind === "navigate") { router.push(a.href); return; }
    if (a.kind === "message") {
      setCommandResult(
        <CommandNote tone={a.tone} title={a.title} body={a.body} />
      );
      return;
    }
    if (a.kind === "migration") {
      const o = a.outcome;
      const st = "status" in o ? o.status : null;
      // Only a migratory verdict opens the map. Linking a resident or
      // under-recorded species to it would put an empty map behind a sentence
      // that just explained there is nothing to draw.
      const href =
        o.kind === "track"
          ? `/migration?species=${encodeURIComponent(a.species.taxon.taxonId)}`
          : undefined;
      setCommandResult(
        <CommandNote
          tone={o.kind === "track" ? "info" : o.kind === "insufficient" ? "warn" : "info"}
          title={`${a.species.taxon.commonName} — ${statusLabel(st)}`}
          body={o.kind === "track" ? evidenceLine(st) : o.message}
          footer={o.kind === "track" ? undefined : evidenceLine(st)}
          href={href}
          hrefLabel="View migration map →"
          onNavigate={() => href && router.push(href)}
        />
      );
      return;
    }
    if (a.kind === "agent") { router.push(`/chat?q=${encodeURIComponent(a.question)}`); return; }
    if (a.kind === "help") {
      setCommandResult(
        <CommandNote
          tone="info"
          title="Commands"
          body={COMMANDS.map(c => `${c.verb} — ${c.summary}`).join("\n")}
        />
      );
    }
  };

  const handleImageUpload = async (file: File) => {
    if (!file.type.startsWith("image/")) return;
    setImagePreview(URL.createObjectURL(file));
    setVisionLoading(true);
    setVisionError(null);
    setVisionStatus("Identifying with Gemini…");
    try {
      // Identification runs server-side: the model call and the GBIF lookup both
      // happen in the backend, so no provider key is shipped to the browser.
      setVisionStatus("Identifying species…");
      const parsed = await identifyBird(file);
      console.log("[Vision] identification:", parsed);

      if (!parsed.is_bird || !parsed.scientific_name) {
        setVisionError(
          parsed.is_bird === false
            ? "No bird was detected in this image."
            : "The species could not be identified. Try a clearer photo."
        );
        setVisionLoading(false);
        return;
      }

      setVisionStatus(`Matched: ${parsed.scientific_name}`);
      if (!parsed.gbif_key) {
        setVisionError(
          `Identified "${parsed.scientific_name}" but GBIF has no matching record.`
        );
        setVisionLoading(false);
        return;
      }
      router.push(`/species/${parsed.gbif_key}`);
    } catch (err) {
      console.error("[Vision] top-level error:", err);
      const msg = err instanceof Error ? err.message : String(err);
      if (/\b503\b|overloaded|high demand|UNAVAILABLE/i.test(msg)) {
        setVisionError("Gemini is overloaded right now. Please try again in a moment.");
      } else if (/\b429\b|RESOURCE_EXHAUSTED|quota/i.test(msg)) {
        setVisionError("Gemini API quota exceeded. Check your API key's plan.");
      } else {
        setVisionError("Could not identify species. Please try another image.");
      }
    } finally {
      setVisionLoading(false);
    }
  };

  useEffect(() => {
    if (!uploadMargin) return;
    let timeoutId: NodeJS.Timeout;
    const handleScroll = () => {
      setUploadMargin(false);
    };
    // Wait briefly before adding the listener so the auto-scroll doesn't trigger it
    timeoutId = setTimeout(() => {
       window.addEventListener('wheel', handleScroll, { once: true });
       window.addEventListener('touchmove', handleScroll, { once: true });
    }, 800);

    return () => {
       clearTimeout(timeoutId);
       window.removeEventListener('wheel', handleScroll);
       window.removeEventListener('touchmove', handleScroll);
    };
  }, [uploadMargin]);

  return (
    <div style={{ background: "var(--background)", minHeight: "100vh", paddingTop: 52 }}>

      {/* ── Hero ───────────────────────────────────────────────────────────── */}
      <section style={{ maxWidth: 880, margin: "0 auto", padding: "5rem 1.5rem 3rem" }}>

        {/* Overline */}
        <p style={{
          fontFamily: "var(--font-mono)",
          fontSize: "0.6rem",
          letterSpacing: "0.15em",
          textTransform: "uppercase",
          color: "var(--text-tertiary)",
          marginBottom: "2rem",
          fontWeight: 500,
        }}>
          Ecological Intelligence Platform
        </p>

        {/* Title — reduced 15% from prior 6.5rem cap */}
        <h1 style={{
          fontFamily: "var(--font-display)",
          fontSize: "clamp(3.2rem, 6.8vw, 5.5rem)",
          fontWeight: 500,
          lineHeight: 1.05,
          letterSpacing: "-0.015em",
          color: "var(--text-primary)",
          marginBottom: "1.75rem",
        }}>
          Bird Research.<br />
          <em style={{ fontStyle: "italic", color: "var(--accent-secondary)", fontWeight: 500 }}>
            Seamlessly Integrated.
          </em>
        </h1>

        {/* Subhead */}
        <p style={{
          fontFamily: "var(--font-sans)",
          fontSize: "1rem",
          lineHeight: 1.65,
          color: "var(--text-secondary)",
          maxWidth: 480,
          marginBottom: "3.25rem",
          fontWeight: 400,
        }}>
          Move beyond identification. Understand population change.
          Ten years of GBIF occurrence data, visualized migration corridors, and AI-driven analysis. One unified platform.
        </p>

        {/* ── Search ─────────────────────────────────────────────────────── */}
        <div style={{ position: "relative", marginBottom: "0.5rem" }}>
          <input
            type="text"
            value={query}
            onChange={(e) => { setCommandResult(null); handleSearch(e.target.value); }}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void runCommand(query); } }}
            placeholder="Search a species, or run a command — try “migration amur falcon”"
            id="species-search-input"
            style={{
              width: "100%",
              background: "var(--surface-raised)",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-lg)",
              color: "var(--text-primary)",
              fontFamily: "var(--font-sans)",
              fontSize: "1rem",
              padding: "0.85rem 2.5rem 0.85rem 1rem",
              outline: "none",
              transition: "border-color 160ms ease",
              boxShadow: "var(--shadow-card)",
            }}
          />
          {loading && (
            <div style={{
              position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)",
              width: 14, height: 14,
              border: "1.5px solid var(--accent-primary)",
              borderTopColor: "transparent",
              borderRadius: "50%",
              animation: "spin 0.7s linear infinite",
            }} />
          )}
        </div>

        {/* What Enter will do. Shown before committing, so a closed command set
            is discoverable instead of something you have to memorise. */}
        {parsed && <CommandPreview parsed={parsed} onPick={(t) => { setQuery(t); void runCommand(t); }} />}
        {running && <CommandNote tone="info" title="Working…" body="" />}
        {commandResult}

        {/* Autocomplete */}
        {results.length > 0 && (
          <div style={{
            background: "var(--surface-raised)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-md)",
            overflow: "hidden",
            marginBottom: "2rem",
            boxShadow: "var(--shadow-card)",
          }}>
            {results.map((s, i) => (
              <button
                key={s.gbif_key}
                onClick={() => router.push(`/species/${s.gbif_key}`)}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "baseline",
                  gap: "1rem",
                  padding: "0.85rem 1rem",
                  textAlign: "left",
                  background: "transparent",
                  border: "none",
                  borderTop: i > 0 ? "1px solid var(--border-subtle)" : "none",
                  cursor: "pointer",
                  transition: "background 120ms ease",
                }}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-muted)")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              >
                <span style={{ fontFamily: "var(--font-sans)", fontSize: "0.9rem", color: "var(--text-primary)", flex: 1, fontWeight: 500 }}>
                  {s.common_name}
                </span>
                <span style={{ fontFamily: "var(--font-sans)", fontSize: "0.875rem", fontStyle: "italic", color: "var(--text-secondary)" }}>
                  {s.scientific_name}
                </span>
                {s.family && (
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
                    {s.family}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* ── Divider ──────────────────────────────────────────────────────── */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "1rem",
          margin: "2.5rem 0",
        }}>
          <div style={{ flex: 1, height: 1, background: "var(--border-subtle)" }} />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "var(--text-tertiary)", fontWeight: 500 }}>
            or identify by photo
          </span>
          <div style={{ flex: 1, height: 1, background: "var(--border-subtle)" }} />
        </div>

        {/* ── Image Upload ──────────────────────────────────────────────────── */}
        <div id="upload-section" ref={uploadRef} style={{ marginBottom: uploadMargin ? "60vh" : "1rem", transition: "margin-bottom 300ms ease" }}>
          <div
            onClick={() => !visionLoading && fileRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f && !visionLoading) handleImageUpload(f); }}
            id="image-upload-zone"
            style={{
              width: "100%",
              border: `2px dashed ${dragOver ? "var(--accent-primary)" : "var(--border)"}`,
              borderRadius: "var(--r-lg)",
              background: dragOver ? "var(--accent-muted)" : "var(--surface)",
              cursor: visionLoading ? "default" : "pointer",
              overflow: "hidden",
              transition: "border-color 160ms ease, background 160ms ease",
            }}
          >
            {imagePreview && visionLoading ? (
              <div style={{ position: "relative" }}>
                <img
                  src={imagePreview}
                  alt="Uploading"
                  style={{ width: "100%", objectFit: "cover", maxHeight: 220, filter: "brightness(0.55)" }}
                />
                <div style={{
                  position: "absolute", inset: 0,
                  display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10,
                }}>
                  <div style={{
                    width: 18, height: 18,
                    border: "1.5px solid #FFFFFF", borderTopColor: "transparent",
                    borderRadius: "50%",
                    animation: "spin 0.7s linear infinite",
                  }} />
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", letterSpacing: "0.12em", color: "#FFFFFF", textTransform: "uppercase" }}>
                    {visionStatus}
                  </p>
                </div>
              </div>
            ) : (
              <div style={{
                padding: "2.75rem 1rem",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "0.5rem",
              }}>
                <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.9rem", color: "var(--text-tertiary)" }}>
                  Drag & drop a bird photo, or click to browse
                </p>
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.58rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
                  JPG · PNG · WEBP
                </p>
              </div>
            )}
          </div>
          <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }}
            onChange={e => { const f = e.target.files?.[0]; if (f) handleImageUpload(f); }} />

          {visionError && (
            <p style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.65rem",
              color: "var(--danger)",
              marginTop: "0.5rem",
              letterSpacing: "0.04em",
            }}>
              ↳ {visionError}
            </p>
          )}
        </div>
      </section>

      {/* ── Capabilities — table of contents ──────────────────────────────── */}
      <section style={{ background: "var(--surface)", marginTop: "2rem" }}>
        <div style={{ maxWidth: 880, margin: "0 auto", padding: "4rem 1.5rem 6rem" }}>

          <p style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.6rem",
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--text-tertiary)",
            marginBottom: "2rem",
            fontWeight: 500,
          }}>
            Platform capabilities
          </p>

          {CAPABILITIES.map(({ index, label, detail, href }, i) => {
            const isVision = index === "V";
            const isClickable = href || isVision;
            const row = (
              <div
                key={index}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: "1.5rem",
                  padding: "1.15rem 1rem",
                  borderBottom: "1px solid var(--border-subtle)",
                  borderLeft: "2px solid transparent",
                  cursor: isClickable ? "pointer" : "default",
                  transition: "background 140ms ease, border-color 140ms ease",
                  marginLeft: -1,
                }}
                onMouseEnter={e => {
                  if (isClickable) {
                    (e.currentTarget as HTMLElement).style.background = "var(--accent-muted)";
                    (e.currentTarget as HTMLElement).style.borderLeftColor = "var(--accent-primary)";
                  }
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.background = "transparent";
                  (e.currentTarget as HTMLElement).style.borderLeftColor = "transparent";
                }}
                onClick={() => {
                  if (isVision) {
                    setUploadMargin(true);
                    setTimeout(() => {
                      uploadRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }, 50);
                  } else if (href) {
                    router.push(href);
                  }
                }}
              >
                <span style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  letterSpacing: "0.06em",
                  color: "var(--text-tertiary)",
                  minWidth: "2rem",
                  fontWeight: 500,
                }}>
                  {index}.
                </span>
                <span style={{
                  fontFamily: "var(--font-sans)",
                  fontSize: "1.05rem",
                  fontWeight: 500,
                  color: "var(--text-primary)",
                  flex: 1,
                  lineHeight: 1.3,
                }}>
                  {label}
                </span>
                <span style={{
                  fontFamily: "var(--font-sans)",
                  fontSize: "0.85rem",
                  color: "var(--text-secondary)",
                  maxWidth: "18rem",
                  textAlign: "right",
                  lineHeight: 1.5,
                }}>
                  {detail}
                </span>
                {isClickable && (
                  <span style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.85rem",
                    color: "var(--accent-secondary)",
                    flexShrink: 0,
                  }}>{isVision ? "↑" : "→"}</span>
                )}
              </div>
            );
            return href
              ? <a key={index} href={href} style={{ textDecoration: "none", display: "block" }}>{row}</a>
              : row;
          })}
        </div>
      </section>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

/* ── Command bar presentation ─────────────────────────────────────────────── */

function CommandNote({
  tone, title, body, footer, href, hrefLabel, onNavigate,
}: {
  tone: "info" | "warn";
  title: string;
  body: string;
  footer?: string;
  /** When set, the whole card is a link to the view that renders this result. */
  href?: string;
  hrefLabel?: string;
  onNavigate?: () => void;
}) {
  const clickable = Boolean(href);
  return (
    <div
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? onNavigate : undefined}
      onKeyDown={
        clickable
          ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onNavigate?.(); } }
          : undefined
      }
      style={{
      border: `1px solid ${tone === "warn" ? "var(--accent-danger, #c0563a)" : "var(--border)"}`,
      borderRadius: "var(--r-md)",
      background: "var(--surface-raised)",
      padding: "0.9rem 1rem",
      marginBottom: "1rem",
      boxShadow: "var(--shadow-card)",
      cursor: clickable ? "pointer" : undefined,
    }}>
      <div style={{ fontWeight: 600, color: tone === "warn" ? "var(--accent-danger, #c0563a)" : "var(--text-primary)" }}>
        {title}
      </div>
      {body && (
        <div style={{ marginTop: "0.35rem", whiteSpace: "pre-line", color: "var(--text-secondary)", fontSize: "0.92rem" }}>
          {body}
        </div>
      )}
      {footer && (
        <div style={{ marginTop: "0.4rem", color: "var(--text-tertiary, #778)", fontSize: "0.8rem" }}>
          {footer}
        </div>
      )}
      {clickable && (
        <div style={{ marginTop: "0.55rem", color: "var(--accent-primary)", fontSize: "0.85rem", fontWeight: 600 }}>
          {hrefLabel ?? "Open →"}
        </div>
      )}
    </div>
  );
}

function CommandPreview({
  parsed, onPick,
}: { parsed: ParseResult; onPick: (text: string) => void }) {
  if (parsed.kind === "command") {
    const args = [
      ...parsed.species.map((sp) => sp.taxon.commonName),
      ...Object.entries(parsed.values).map(([k, v]) => `${k}: ${v}`),
    ];
    const first = parsed.species[0];
    return (
      <div style={{ marginBottom: "1rem", fontSize: "0.9rem", color: "var(--text-secondary)" }}>
        <strong style={{ color: "var(--accent-primary)" }}>{parsed.spec.verb}</strong>
        {args.length > 0 && <> · {args.join(", ")}</>}
        {/* The resolved name is always shown back, never silently substituted. */}
        {first && first.confidence < 1 && (
          <> · matched “{first.matchedAlias}” ({(first.confidence * 100).toFixed(0)}%)</>
        )}
        {parsed.unavailable && (
          <div style={{ color: "var(--accent-danger, #c0563a)", marginTop: 4 }}>{parsed.unavailable}</div>
        )}
        <span style={{ opacity: 0.6 }}> — press Enter</span>
      </div>
    );
  }

  if (parsed.kind === "disambiguate") {
    return (
      <div style={{
        border: "1px solid var(--border)", borderRadius: "var(--r-md)",
        background: "var(--surface-raised)", marginBottom: "1rem", overflow: "hidden",
      }}>
        <div style={{ padding: "0.6rem 1rem", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
          Several species match “{parsed.input}” — which one?
        </div>
        {parsed.resolution.candidates.map((c) => (
          <button
            key={c.taxon.taxonId}
            onClick={() => onPick(parsed.spec ? `${parsed.spec.verb} ${c.taxon.commonName}` : c.taxon.commonName)}
            style={{
              width: "100%", textAlign: "left", padding: "0.6rem 1rem", border: "none",
              background: "transparent", cursor: "pointer", fontFamily: "var(--font-sans)",
              fontSize: "0.92rem", color: "var(--text-primary)",
            }}
          >
            <strong>{c.taxon.commonName}</strong>{" "}
            <span style={{ color: "var(--text-tertiary, #778)" }}>
              {c.taxon.scientificName} · {(c.confidence * 100).toFixed(0)}%
            </span>
          </button>
        ))}
      </div>
    );
  }

  if (parsed.kind === "fallback") {
    return (
      <div style={{ marginBottom: "1rem", fontSize: "0.9rem", color: "var(--text-secondary)" }}>
        {parsed.reason === "unresolved-species"
          ? "No species matches that name."
          : "No command matches — Enter asks the research agent."}
      </div>
    );
  }
  return null;
}
