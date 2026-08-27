import { useRef, useEffect, useState } from 'react';

export function ChatInput({ 
  onSend, 
  disabled 
}: { 
  onSend: (text: string) => void;
  disabled: boolean;
}) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!disabled && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [disabled]);

  const handleSend = () => {
    if (!input.trim() || disabled) return;
    onSend(input);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { 
      e.preventDefault(); 
      handleSend(); 
    }
  };

  return (
    <div style={{
      borderTop: "1px solid var(--border)",
      padding: "1rem 1.5rem 1.25rem",
      background: "var(--background)",
      flexShrink: 0,
    }}>
      <div style={{
        maxWidth: 720,
        margin: "0 auto",
        display: "flex",
        alignItems: "flex-end",
        gap: "0.6rem",
        background: "var(--surface-raised)",
        border: `1px solid ${input.trim() && !disabled ? "var(--accent-primary)" : "var(--border)"}`,
        borderRadius: "16px",
        padding: "0.55rem 0.55rem 0.55rem 0.85rem",
        transition: "border-color 160ms ease",
        opacity: disabled ? 0.7 : 1,
        boxShadow: "var(--shadow-card)",
      }}>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? "Querying ecological records…" : "Ask about a population anomaly, migration pattern, or conservation event…"}
          rows={1}
          disabled={disabled}
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            resize: "none",
            fontFamily: "var(--font-sans, 'DM Sans')",
            fontSize: "0.95rem",
            color: disabled ? "var(--text-tertiary)" : "var(--text-primary)",
            lineHeight: 1.5,
            maxHeight: 120,
            cursor: disabled ? "default" : "text",
            padding: "0.35rem 0",
          }}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || disabled}
          style={{
            fontFamily: "var(--font-mono, monospace)",
            fontSize: "0.65rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: input.trim() && !disabled ? "var(--text-on-accent)" : "var(--text-tertiary)",
            background: input.trim() && !disabled ? "var(--accent-primary)" : "var(--surface)",
            border: "none",
            borderRadius: "8px",
            cursor: input.trim() && !disabled ? "pointer" : "default",
            padding: "0.5rem 0.9rem",
            transition: "background 140ms ease",
            flexShrink: 0,
            fontWeight: 600,
          }}
          onMouseEnter={e => {
            if (input.trim() && !disabled) e.currentTarget.style.background = "var(--accent-secondary)";
          }}
          onMouseLeave={e => {
            if (input.trim() && !disabled) e.currentTarget.style.background = "var(--accent-primary)";
          }}
        >
          {disabled ? "…" : "Send ↵"}
        </button>
      </div>
      <p style={{
        fontFamily: "var(--font-mono, monospace)",
        fontSize: "0.7rem",
        letterSpacing: "0.04em",
        color: "var(--text-tertiary)",
        maxWidth: 720,
        margin: "0.5rem auto 0",
      }}>
        ↵ send · ⇧↵ newline · data via GBIF + Open-Meteo
      </p>
    </div>
  );
}
