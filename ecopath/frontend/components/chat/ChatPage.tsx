import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { getGBIFSpeciesDetail } from '@/lib/api';
import { useSSEChat } from '../../hooks/useSSEChat';
import { ChatMessageList } from './ChatMessageList';
import { ChatInput } from './ChatInput';
import { SessionContextBar } from './SessionContextBar';
import { NewConversationButton } from './NewConversationButton';

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

export function ChatPageInner() {
  const searchParams = useSearchParams();
  const speciesId = searchParams.get("species");
  const yearContext = searchParams.get("year");

  // NEXT_PUBLIC_CHAT_MOCK=1 swaps in the local mock stream (app/api/mock-chat),
  // so the block renderers can be worked on without the Python agent running.
  // The mock has no session store, so it gets no reset endpoint.
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  const endpoints = process.env.NEXT_PUBLIC_CHAT_MOCK
    ? { streamUrl: '/api/mock-chat' }
    : { streamUrl: `${apiBase}/api/chat/stream`, resetUrl: `${apiBase}/api/chat/reset` };

  const { messages, isConnected, sessionState, contextPulse, sendMessage, resetConversation } =
    useSSEChat(endpoints);

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
      {/* Header */}
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
            fontFamily: "var(--font-display, 'Playfair Display')",
            fontSize: "1rem",
            fontWeight: 600,
            color: "var(--text-primary)",
          }}>
            JARVIS Ecological Agent
          </span>
          <span style={{
            fontFamily: "var(--font-mono, monospace)",
            fontSize: "0.6rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--accent-primary)",
            background: "var(--accent-muted)",
            border: "1px solid var(--accent-primary)",
            padding: "2px 8px",
            borderRadius: "4px",
            fontWeight: 600,
          }}>
            Groq · gpt-oss-120b
          </span>
        </div>

        {messages.length > 0 && <NewConversationButton onConfirm={resetConversation} />}
      </div>

      {/* Live research focus, driven by the backend session state */}
      <SessionContextBar state={sessionState} pulseKey={contextPulse} />

      {/* Context Band — the species this page was opened for */}
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
            fontFamily: "var(--font-mono, monospace)",
            fontSize: "0.6rem",
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--text-tertiary)",
            fontWeight: 500,
          }}>
            Context ›
          </span>
          <span style={{ fontFamily: "var(--font-sans, 'DM Sans')", fontSize: "0.85rem", color: "var(--text-primary)", fontWeight: 500 }}>
            {speciesName}
          </span>
          {speciesScientific && (
            <span style={{ fontFamily: "var(--font-sans, 'DM Sans')", fontSize: "0.875rem", fontStyle: "italic", color: "var(--text-secondary)" }}>
              {speciesScientific}
            </span>
          )}
          {yearContext && (
            <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: "0.6rem", color: "var(--text-tertiary)", marginLeft: "auto", letterSpacing: "0.08em" }}>
              year {yearContext}
            </span>
          )}
        </div>
      )}

      {/* Main Content Area */}
      {messages.length === 0 ? (
        <div style={{ flex: 1, padding: "2.5rem 1.5rem", overflowY: "auto", maxWidth: 720, margin: "0 auto", width: "100%" }}>
          <div style={{ paddingTop: "1rem" }}>
            <p style={{
              fontFamily: "var(--font-display, 'Playfair Display')",
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
              fontFamily: "var(--font-sans, 'DM Sans')",
              fontSize: "0.875rem",
              fontStyle: "italic",
              color: "var(--text-secondary)",
              marginBottom: "2.75rem",
            }}>
              Ecological data retrieved dynamically via tools · Reasoned by Groq
            </p>

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
                    borderRadius: "12px",
                    boxShadow: "var(--shadow-card)",
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = "var(--accent-primary)";
                    e.currentTarget.style.background = "var(--accent-muted)";
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = "var(--border)";
                    e.currentTarget.style.background = "var(--surface-raised)";
                  }}
                >
                  <span style={{
                    fontFamily: "var(--font-sans, 'DM Sans')",
                    fontSize: "0.9rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.5,
                  }}>
                    {s}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <ChatMessageList
          messages={messages}
          onFollowUp={(text) => sendMessage(text, { fromFollowUp: true })}
        />
      )}

      {/* Input Box */}
      <ChatInput onSend={sendMessage} disabled={isConnected} />
    </div>
  );
}
