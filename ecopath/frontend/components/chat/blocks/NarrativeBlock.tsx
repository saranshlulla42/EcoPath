import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { NarrativeBlock as NarrativeBlockType } from '../../../types/chat';

function preprocessResponse(text: string): string {
  if (!text) return "";
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

export function NarrativeBlockView({ block }: { block: NarrativeBlockType }) {
  const processed = preprocessResponse(block.content);

  return (
    <div style={{
      fontFamily: "var(--font-sans, 'DM Sans', sans-serif)",
      fontSize: "0.95rem",
      lineHeight: 1.65,
      color: "var(--text-primary)",
    }}>
      {processed ? (
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children }) => (
              <p style={{ marginBottom: "0.85rem" }}>{children}</p>
            ),
            strong: ({ children }) => {
              const text = String(children);
              if (text === "STATISTICAL") return <span className="evidence-tag evidence-stat">Statistical</span>;
              if (text === "CLIMATE") return <span className="evidence-tag evidence-climate">Climate</span>;
              if (text === "FIELD NOTE") return <span className="evidence-tag evidence-fact">Field Note</span>;
              if (text === "HYPOTHESIS") return <span className="evidence-tag evidence-hypo">Hypothesis</span>;
              return <strong style={{ color: "var(--text-primary)", fontWeight: 600 }}>{children}</strong>;
            },
            code: ({ children }) => {
              const text = String(children);
              if (text === "STATISTICAL") return <span className="evidence-tag evidence-stat">Statistical</span>;
              if (text === "CLIMATE") return <span className="evidence-tag evidence-climate">Climate</span>;
              if (text === "FIELD NOTE") return <span className="evidence-tag evidence-fact">Field Note</span>;
              if (text === "HYPOTHESIS") return <span className="evidence-tag evidence-hypo">Hypothesis</span>;
              return (
                <code style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.85em",
                  color: "var(--accent-primary)",
                  background: "var(--surface)",
                  padding: "2px 6px",
                  borderRadius: "4px",
                }}>
                  {children}
                </code>
              );
            },
            a: ({ children, href }) => (
              <a href={href} style={{ color: "var(--accent-primary)", textDecoration: "underline" }}
                 onMouseEnter={e => e.currentTarget.style.color = 'var(--accent-secondary)'}
                 onMouseLeave={e => e.currentTarget.style.color = 'var(--accent-primary)'}
              >{children}</a>
            ),
            ul: ({ children }) => (
              <ul style={{ paddingLeft: "1.2rem", marginBottom: "0.85rem" }}>{children}</ul>
            ),
            li: ({ children }) => (
              <li style={{ marginBottom: "0.3rem" }}>{children}</li>
            ),
            em: ({ children }) => <em style={{ fontStyle: "italic", color: "var(--text-secondary)" }}>{children}</em>,
          }}
        >
          {processed}
        </ReactMarkdown>
      ) : null}

      {block.isStreaming && (
        <span className="streaming-cursor">▊</span>
      )}

      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        .streaming-cursor {
          display: inline;
          animation: blink 0.8s step-end infinite;
          color: var(--accent-primary);
          font-weight: 300;
          margin-left: 2px;
        }
      `}</style>
    </div>
  );
}
