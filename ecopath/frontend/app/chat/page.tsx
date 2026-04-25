"use client";

import { useState, useRef, useEffect, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getGBIFSpeciesDetail } from "@/lib/api";
import { streamChat } from "@/lib/api";
import { RotateCcw } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// ── Generic suggestions (no species context) ──────────────────────────────────
const GENERIC_SUGGESTIONS = [
  "Why did Greater Flamingo populations dip in Gujarat in 2020?",
  "What environmental factors drive Amur Falcon migration through Nagaland?",
  "Explain the population surge of Demoiselle Cranes in Rajasthan.",
  "How does monsoon variability affect wetland bird populations in India?",
  "Why are vulture populations in India critically endangered?",
];

function buildSpeciesSuggestions(commonName: string, scientificName: string, family?: string): string[] {
  const f = family ? ` (family ${family})` : "";
  return [
    `Why did ${commonName} populations change significantly in recent years?`,
    `What are the primary conservation threats facing the ${commonName}?`,
    `How does climate change affect ${commonName}${f} migration and breeding timing?`,
    `What habitats does the ${commonName} depend on, and how are they at risk?`,
    `Explain any population anomalies detected in GBIF data for the ${commonName}.`,
  ];
}

// ── Evidence tag preprocessor — strips emoji, elevates labels ─────────────────
function preprocessResponse(text: string): string {
  return text
    .replace(/📊\s*\*?\*?Statistical evidence[^)]*\)?:?\*?\*?/gi, "**`STATISTICAL`**")
    .replace(/📊\s*/g, "**`STATISTICAL`** ")
    .replace(/🌦️\s*\*?\*?Weather\/climate evidence[^)]*\)?:?\*?\*?/gi, "**`CLIMATE`**")
    .replace(/🌦️\s*/g, "**`CLIMATE`** ")
    .replace(/📚\s*\*?\*?Known ecological fact:?\*?\*?/gi, "**`FIELD NOTE`**")
    .replace(/📚\s*/g, "**`FIELD NOTE`** ")
    .replace(/🔬\s*\*?\*?Scientific hypothesis:?\*?\*?/gi, "**`HYPOTHESIS`**")
    .replace(/🔬\s*/g, "**`HYPOTHESIS`** ")
    .replace(/⏳\s*\*Retrieving ecological context\.\.\.\*/g, "")
    .replace(/🧠\s*\*Analyzing data with Gemini[^*]*\*/g, "")
    .replace(/---\n\n/g, "")
    .trim();
}

// ── Typing indicator ──────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "0.6rem 0" }}>
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </div>
  );
}

// ── User message ──────────────────────────────────────────────────────────────
function UserMessage({ content }: { content: string }) {
  return (
    <div className="chat-bubble" style={{ display: "flex", justifyContent: "flex-end", marginBottom: "1.5rem" }}>
      <div style={{
        maxWidth: "62%",
        padding: "0.75rem 1rem",
        background: "var(--accent-muted)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-lg)",
        fontFamily: "var(--font-sans)",
        fontSize: "0.9rem",
        lineHeight: 1.6,
        color: "var(--text-primary)",
      }}>
        {content}
      </div>
    </div>
  );
}

// ── Assistant message ─────────────────────────────────────────────────────────
function AssistantMessage({ content, streaming }: { content: string; streaming?: boolean }) {
  const processed = preprocessResponse(content);
  return (
    <div className="chat-bubble" style={{ display: "flex", gap: "1rem", marginBottom: "2rem", alignItems: "flex-start" }}>
      {/* Left accent bar */}
      <div style={{
        width: 2,
        background: "var(--accent-primary)",
        borderRadius: 1,
        flexShrink: 0,
        marginTop: 4,
        alignSelf: "stretch",
        minHeight: 20,
      }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontFamily: "var(--font-sans)",
          fontSize: "0.92rem",
          lineHeight: 1.75,
          color: "var(--text-primary)",
        }}>
          {processed ? (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => (
                  <p style={{ marginBottom: "0.85rem", fontFamily: "var(--font-sans)", lineHeight: 1.75, color: "var(--text-primary)" }}>{children}</p>
                ),
                strong: ({ children }) => {
                  const text = String(children);
                  if (text === "STATISTICAL")  return <span className="evidence-tag evidence-stat">Statistical</span>;
                  if (text === "CLIMATE")      return <span className="evidence-tag evidence-climate">Climate</span>;
                  if (text === "FIELD NOTE")   return <span className="evidence-tag evidence-fact">Field Note</span>;
                  if (text === "HYPOTHESIS")   return <span className="evidence-tag evidence-hypo">Hypothesis</span>;
                  return <strong style={{ color: "var(--text-primary)", fontWeight: 600 }}>{children}</strong>;
                },
                code: ({ children }) => {
                  const text = String(children);
                  if (text === "STATISTICAL")  return <span className="evidence-tag evidence-stat">Statistical</span>;
                  if (text === "CLIMATE")      return <span className="evidence-tag evidence-climate">Climate</span>;
                  if (text === "FIELD NOTE")   return <span className="evidence-tag evidence-fact">Field Note</span>;
                  if (text === "HYPOTHESIS")   return <span className="evidence-tag evidence-hypo">Hypothesis</span>;
                  return (
                    <code style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.78em",
                      color: "var(--accent-primary)",
                      background: "var(--accent-muted)",
                      padding: "1px 5px",
                      borderRadius: "var(--r-sm)",
                    }}>
                      {children}
                    </code>
                  );
                },
                h2: ({ children }) => (
                  <h2 style={{
                    fontFamily: "var(--font-display)",
                    fontSize: "1.1rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    marginTop: "1.5rem",
                    marginBottom: "0.5rem",
                    borderBottom: "1px solid var(--border-subtle)",
                    paddingBottom: "0.3rem",
                  }}>{children}</h2>
                ),
                h3: ({ children }) => (
                  <h3 style={{
                    fontFamily: "var(--font-display)",
                    fontSize: "0.98rem",
                    fontWeight: 500,
                    color: "var(--text-secondary)",
                    marginTop: "1.2rem",
                    marginBottom: "0.3rem",
                  }}>{children}</h3>
                ),
                ul: ({ children }) => (
                  <ul style={{
                    paddingLeft: "1.2rem",
                    marginBottom: "0.85rem",
                    listStyleType: "none",
                  }}>{children}</ul>
                ),
                li: ({ children }) => (
                  <li style={{
                    fontFamily: "var(--font-sans)",
                    fontSize: "0.9rem",
                    lineHeight: 1.65,
                    color: "var(--text-secondary)",
                    marginBottom: "0.3rem",
                    paddingLeft: "0.5rem",
                    borderLeft: "1px solid var(--border-subtle)",
                    marginLeft: "-0.5rem",
                  }}>{children}</li>
                ),
                hr: () => <hr className="field-rule" style={{ margin: "1rem 0" }} />,
                em: ({ children }) => <em style={{ fontStyle: "italic", color: "var(--text-secondary)" }}>{children}</em>,
              }}
            >
              {processed}
            </ReactMarkdown>
          ) : null}
          {streaming && (
            <span style={{
              display: "inline-block",
              width: 6, height: "1em",
              background: "var(--accent-primary)",
              opacity: 0.85,
              verticalAlign: "text-bottom",
              animation: "blink-cursor 1s step-end infinite",
            }} />
          )}
        </div>
      </div>
    </div>
  );
}

function ChatPageInner() {
  const searchParams = useSearchParams();
  const speciesId = searchParams.get("species");
  const yearContext = searchParams.get("year");

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { data: speciesContext } = useQuery({
    queryKey: ["species", speciesId],
    queryFn: () => getGBIFSpeciesDetail(speciesId!),
    enabled: !!speciesId,
  });

  const suggestions = speciesContext
    ? buildSpeciesSuggestions(
        speciesContext.vernacularName ?? speciesContext.canonicalName ?? "this species",
        speciesContext.canonicalName ?? speciesContext.scientificName ?? "",
        speciesContext.family
      )
    : GENERIC_SUGGESTIONS;

  const scrollToBottom = useCallback(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, streamingContent, scrollToBottom]);

  const sendMessage = async (text?: string) => {
    const content = text ?? input.trim();
    if (!content || isStreaming) return;
    setInput("");
    const newMessages: ChatMessage[] = [...messages, { role: "user", content }];
    setMessages(newMessages);
    setIsStreaming(true);
    setStreamingContent("");
    let fullResponse = "";
    try {
      for await (const token of streamChat(newMessages, speciesId ?? undefined, yearContext ? parseInt(yearContext) : undefined)) {
        fullResponse += token;
        setStreamingContent(fullResponse);
      }
      setMessages([...newMessages, { role: "assistant", content: fullResponse }]);
    } catch {
      setMessages([...newMessages, {
        role: "assistant",
        content: "Unable to reach the reasoning agent. Please ensure the backend is running.",
      }]);
    } finally {
      setIsStreaming(false);
      setStreamingContent("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const speciesName = speciesContext?.vernacularName ?? speciesContext?.canonicalName ?? null;
  const speciesScientific = speciesContext?.canonicalName ?? speciesContext?.scientificName ?? null;

  return (
    <div style={{
      paddingTop: 52,
      height: "100vh",
      display: "flex",
      flexDirection: "column",
      background: "var(--background)",
    }}>

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div style={{
        borderBottom: "1px solid var(--border)",
        padding: "0.85rem 1.5rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexShrink: 0,
        background: "var(--background)",
        gap: "0.75rem",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
          <span style={{
            fontFamily: "var(--font-display)",
            fontSize: "1rem",
            fontWeight: 600,
            color: "var(--text-primary)",
          }}>
            Reasoning Agent
          </span>
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.6rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--accent-primary)",
            background: "var(--accent-muted)",
            border: "1px solid var(--border)",
            padding: "2px 8px",
            borderRadius: "var(--r-sm)",
            fontWeight: 500,
          }}>
            Gemini
          </span>
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.6rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--accent-primary)",
            background: "var(--accent-muted)",
            border: "1px solid var(--border)",
            padding: "2px 8px",
            borderRadius: "var(--r-sm)",
            fontWeight: 500,
          }}>
            RAG
          </span>
        </div>

        {messages.length > 0 && (
          <button
            onClick={() => { setMessages([]); setStreamingContent(""); }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              fontFamily: "var(--font-mono)",
              fontSize: "0.62rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "var(--text-secondary)",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              padding: "0.25rem 0",
              transition: "color 120ms ease",
              fontWeight: 500,
            }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--accent-primary)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-secondary)")}
          >
            <RotateCcw size={11} />
            New session
          </button>
        )}
      </div>

      {/* ── Species context band ───────────────────────────────────────────── */}
      {speciesName && (
        <div style={{
          background: "var(--surface)",
          borderBottom: "1px solid var(--border)",
          padding: "0.55rem 1.5rem",
          display: "flex",
          alignItems: "baseline",
          gap: "0.75rem",
          flexShrink: 0,
        }}>
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.6rem",
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--text-tertiary)",
            fontWeight: 500,
          }}>
            Context ›
          </span>
          <span style={{ fontFamily: "var(--font-sans)", fontSize: "0.85rem", color: "var(--text-primary)", fontWeight: 500 }}>
            {speciesName}
          </span>
          {speciesScientific && (
            <span style={{ fontFamily: "var(--font-sans)", fontSize: "0.875rem", fontStyle: "italic", color: "var(--text-tertiary)" }}>
              {speciesScientific}
            </span>
          )}
          {yearContext && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", color: "var(--text-tertiary)", marginLeft: "auto", letterSpacing: "0.08em" }}>
              year {yearContext}
            </span>
          )}
        </div>
      )}

      {/* ── Thread ────────────────────────────────────────────────────────── */}
      <div
        ref={threadRef}
        className="chat-thread"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "2.5rem 1.5rem",
          maxWidth: 740,
          width: "100%",
          margin: "0 auto",
          alignSelf: "stretch",
          boxSizing: "border-box",
        }}
      >

        {/* Welcome state */}
        {messages.length === 0 && !isStreaming && (
          <div style={{ paddingTop: "1rem" }}>
            {/* Welcome title */}
            <p style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(1.55rem, 3.4vw, 2.4rem)",
              fontWeight: 500,
              color: "var(--text-primary)",
              lineHeight: 1.15,
              marginBottom: "0.5rem",
              letterSpacing: "-0.01em",
            }}>
              {speciesName ? `Query the record for ${speciesName}.` : "Query the field record."}
            </p>
            <p style={{
              fontFamily: "var(--font-sans)",
              fontSize: "0.875rem",
              fontStyle: "italic",
              color: "var(--text-tertiary)",
              marginBottom: "2.75rem",
            }}>
              Ecological data retrieved from GBIF + Open-Meteo · Reasoned by Gemini
            </p>

            {/* Suggestion list */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.85rem",
                    padding: "0.85rem 1rem",
                    background: "var(--surface-raised)",
                    border: "1px solid var(--border)",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "border-color 140ms ease, background 140ms ease",
                    borderRadius: "var(--r-md)",
                    boxShadow: "var(--shadow-card)",
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = "var(--accent-primary)";
                    const dash = e.currentTarget.firstChild as HTMLElement;
                    const text = e.currentTarget.lastChild as HTMLElement;
                    if (dash) dash.style.background = "var(--accent-primary)";
                    if (text) text.style.color = "var(--text-primary)";
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = "var(--border)";
                    const dash = e.currentTarget.firstChild as HTMLElement;
                    const text = e.currentTarget.lastChild as HTMLElement;
                    if (dash) dash.style.background = "var(--accent-muted)";
                    if (text) text.style.color = "var(--text-secondary)";
                  }}
                >
                  <span style={{
                    width: 16,
                    height: 2,
                    background: "var(--accent-muted)",
                    flexShrink: 0,
                    transition: "background 140ms ease",
                    borderRadius: 1,
                  }} />
                  <span style={{
                    fontFamily: "var(--font-sans)",
                    fontSize: "0.9rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.5,
                    transition: "color 140ms ease",
                  }}>
                    {s}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Messages */}
        {messages.map((msg, i) =>
          msg.role === "user"
            ? <UserMessage key={i} content={msg.content} />
            : <AssistantMessage key={i} content={msg.content} />
        )}

        {/* Streaming */}
        {isStreaming && (
          streamingContent
            ? <AssistantMessage content={streamingContent} streaming />
            : (
              <div style={{ display: "flex", alignItems: "flex-start", gap: "1rem", marginBottom: "1.5rem" }}>
                <div style={{ width: 2, background: "var(--accent-primary)", opacity: 0.5, borderRadius: 1, alignSelf: "stretch", minHeight: 20 }} />
                <TypingIndicator />
              </div>
            )
        )}
      </div>

      {/* ── Input ─────────────────────────────────────────────────────────── */}
      <div style={{
        borderTop: "1px solid var(--border)",
        padding: "1rem 1.5rem 1.25rem",
        background: "var(--background)",
        flexShrink: 0,
      }}>
        <div style={{
          maxWidth: 740,
          margin: "0 auto",
          display: "flex",
          alignItems: "flex-end",
          gap: "0.6rem",
          background: "var(--surface-raised)",
          border: `1px solid ${input.trim() ? "var(--accent-primary)" : "var(--border)"}`,
          borderRadius: "var(--r-lg)",
          padding: "0.55rem 0.55rem 0.55rem 0.85rem",
          transition: "border-color 160ms ease",
          boxShadow: "var(--shadow-card)",
        }}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isStreaming ? "Querying ecological records…" : "Ask about a population anomaly, migration pattern, or conservation event…"}
            rows={1}
            id="chat-input"
            disabled={isStreaming}
            style={{
              flex: 1,
              background: "transparent",
              border: "none",
              outline: "none",
              resize: "none",
              fontFamily: "var(--font-sans)",
              fontSize: "0.9rem",
              color: isStreaming ? "var(--text-tertiary)" : "var(--text-primary)",
              lineHeight: 1.5,
              maxHeight: 120,
              cursor: isStreaming ? "default" : "text",
              padding: "0.35rem 0",
            }}
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || isStreaming}
            id="chat-send-button"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.62rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: input.trim() && !isStreaming ? "var(--text-on-accent)" : "var(--text-tertiary)",
              background: input.trim() && !isStreaming ? "var(--accent-primary)" : "var(--surface)",
              border: "none",
              borderRadius: "var(--r-md)",
              cursor: input.trim() && !isStreaming ? "pointer" : "default",
              padding: "0.5rem 0.9rem",
              transition: "background 140ms ease",
              flexShrink: 0,
              fontWeight: 500,
            }}
            onMouseEnter={e => {
              if (input.trim() && !isStreaming) e.currentTarget.style.background = "var(--accent-secondary)";
            }}
            onMouseLeave={e => {
              if (input.trim() && !isStreaming) e.currentTarget.style.background = "var(--accent-primary)";
            }}
          >
            {isStreaming ? "…" : "Send ↵"}
          </button>
        </div>
        <p style={{
          fontFamily: "var(--font-mono)",
          fontSize: "0.7rem",
          letterSpacing: "0.04em",
          color: "var(--text-tertiary)",
          maxWidth: 740,
          margin: "0.5rem auto 0",
        }}>
          ↵ send · ⇧↵ newline · data via GBIF + Open-Meteo
        </p>
      </div>

      <style>{`
        @keyframes blink-cursor {
          0%, 49% { opacity: 0.8; }
          50%, 100% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={
      <div style={{ paddingTop: 48, height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-primary)" }}>
        <div style={{ width: 16, height: 16, border: "1px solid var(--accent-primary)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    }>
      <ChatPageInner />
    </Suspense>
  );
}
