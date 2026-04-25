"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { searchSpecies } from "@/lib/api";
import { GoogleGenerativeAI } from "@google/generative-ai";
import type { GBIFSearchResult } from "@/lib/types";

const genAI = new GoogleGenerativeAI(process.env.NEXT_PUBLIC_GEMINI_API_KEY ?? "");

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

  const handleImageUpload = async (file: File) => {
    if (!file.type.startsWith("image/")) return;
    setImagePreview(URL.createObjectURL(file));
    setVisionLoading(true);
    setVisionError(null);
    setVisionStatus("Identifying with Gemini…");
    try {
      const base64String = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve((reader.result as string).split(",")[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash-lite" });
      const parts = [
        { inlineData: { data: base64String, mimeType: file.type } },
        {
          text: `You are an expert ornithologist. Identify the bird in this image.
Respond with ONLY a JSON object, no markdown fences, no extra text:
{"is_bird":true,"scientific_name":"Genus species","common_name":"Name","confidence":0.0}
If you cannot identify it or it is not a bird, respond:
{"is_bird":false,"scientific_name":null,"common_name":null,"confidence":0.0}`,
        },
      ];

      const MAX_ATTEMPTS = 4;
      let result: Awaited<ReturnType<typeof model.generateContent>> | null = null;
      let lastErr: unknown = null;
      for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
        try {
          result = await model.generateContent(parts);
          break;
        } catch (e) {
          lastErr = e;
          const msg = e instanceof Error ? e.message : String(e);
          const transient = /\b(503|429|overloaded|high demand|UNAVAILABLE|RESOURCE_EXHAUSTED)\b/i.test(msg);
          console.warn(`[Vision] attempt ${attempt} failed (transient=${transient}):`, msg);
          if (!transient || attempt === MAX_ATTEMPTS) throw e;
          const backoff = Math.round(500 * 2 ** (attempt - 1) + Math.random() * 250);
          setVisionStatus(`Gemini is busy, retrying (attempt ${attempt + 1}/${MAX_ATTEMPTS})…`);
          await new Promise((r) => setTimeout(r, backoff));
        }
      }
      if (!result) throw lastErr ?? new Error("Gemini call failed");

      const finishReason = result.response.candidates?.[0]?.finishReason;
      const rawText = result.response.text();
      console.log("[Vision] finishReason:", finishReason);
      console.log("[Vision] raw Gemini response:", rawText);

      const raw = rawText.replace(/```json\n?|\n?```/g, "").trim();
      let parsed: { is_bird: boolean; scientific_name: string | null; common_name: string | null; confidence: number };
      try {
        parsed = JSON.parse(raw);
      } catch (parseErr) {
        console.error("[Vision] JSON parse failed:", parseErr, "raw:", raw);
        parsed = { is_bird: false, scientific_name: null, common_name: null, confidence: 0 };
      }
      console.log("[Vision] parsed:", parsed);

      const scientificName = parsed.is_bird ? parsed.scientific_name : null;
      if (!scientificName) {
        setVisionError(
          parsed.is_bird === false
            ? "Gemini did not detect a bird in this image."
            : "Gemini could not identify the species. Try a clearer photo."
        );
        setVisionLoading(false);
        return;
      }
      setVisionStatus(`Matched: ${scientificName}`);
      const gbifRes = await fetch(`https://api.gbif.org/v1/species/match?name=${encodeURIComponent(scientificName)}&kingdom=Animalia&class=Aves`);
      const gbifData = await gbifRes.json();
      console.log("[Vision] GBIF match:", gbifData);
      if (!gbifData.usageKey) {
        setVisionError(`Gemini identified "${scientificName}" but GBIF has no matching record.`);
        setVisionLoading(false);
        return;
      }
      router.push(`/species/${gbifData.usageKey}`);
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
          Ten years of GBIF occurrence data, visualized migration corridors, and AI-driven analysis — one unified platform.
        </p>

        {/* ── Search ─────────────────────────────────────────────────────── */}
        <div style={{ position: "relative", marginBottom: "0.5rem" }}>
          <input
            type="text"
            value={query}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search any bird species…"
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
