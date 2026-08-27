import { useState } from 'react';
import { RotateCcw } from 'lucide-react';

const LABEL_STYLE: React.CSSProperties = {
  fontFamily: "var(--font-mono, monospace)",
  fontSize: '0.62rem',
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  fontWeight: 500,
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  padding: '0.25rem 0',
  transition: 'color 120ms ease',
};

/**
 * Resets the research session. Subtle by design — most sessions never need it.
 * Confirmation is inline rather than a browser `confirm()` dialog.
 */
export function NewConversationButton({ onConfirm }: { onConfirm: () => void }) {
  const [confirming, setConfirming] = useState(false);

  if (confirming) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem' }}>
        <span
          style={{
            fontFamily: "var(--font-sans, 'DM Sans')",
            fontSize: '0.75rem',
            color: 'var(--text-secondary)',
          }}
        >
          Start a new conversation? Current session will be cleared.
        </span>
        <button
          onClick={() => setConfirming(false)}
          style={{ ...LABEL_STYLE, color: 'var(--text-tertiary)' }}
        >
          Cancel
        </button>
        <button
          onClick={() => {
            setConfirming(false);
            onConfirm();
          }}
          style={{ ...LABEL_STYLE, color: 'var(--accent-primary)', fontWeight: 600 }}
        >
          Confirm
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      title="Start a new conversation"
      style={{
        ...LABEL_STYLE,
        color: 'var(--text-tertiary)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.4rem',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent-primary)')}
      onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-tertiary)')}
    >
      <RotateCcw size={11} />
      New session
    </button>
  );
}
