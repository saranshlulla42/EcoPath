import { useEffect, useRef, useState } from 'react';
import { SessionState } from '../../types/chat';
import { getRegionName } from './blocks/region-labels';

const FADE_MS = 300;

/** Flatten the session state into the "species · regions · years" line. */
function describe(state: SessionState | null): string | null {
  if (!state) return null;

  const segments: string[] = [];
  if (state.species) segments.push(state.species);
  if (state.regions.length > 0) {
    segments.push(state.regions.map(getRegionName).join(', '));
  }
  // The year range alone says nothing useful — it only earns a slot once we
  // know what it applies to.
  if (segments.length > 0 && state.year_range) {
    segments.push(`${state.year_range[0]}–${state.year_range[1]}`);
  }

  return segments.length > 0 ? segments.join('  ·  ') : null;
}

/**
 * Informational strip showing what the agent thinks the conversation is about.
 * Hidden until there is a focus to show. Deliberately not interactive.
 */
export function SessionContextBar({
  state,
  pulseKey = 0,
}: {
  state: SessionState | null;
  /** Bumped when a follow-up chip is clicked, to flash the bar. */
  pulseKey?: number;
}) {
  const incoming = describe(state);
  const [shown, setShown] = useState<string | null>(incoming);
  const [visible, setVisible] = useState(true);
  const [pulsing, setPulsing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cross-fade rather than snapping, so a topic switch reads as a change of
  // subject rather than a glitch.
  useEffect(() => {
    if (incoming === shown) return;

    if (shown === null) {
      setShown(incoming);
      setVisible(true);
      return;
    }

    setVisible(false);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setShown(incoming);
      setVisible(true);
    }, FADE_MS);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [incoming, shown]);

  useEffect(() => {
    if (pulseKey === 0) return;
    setPulsing(true);
    const t = setTimeout(() => setPulsing(false), 600);
    return () => clearTimeout(t);
  }, [pulseKey]);

  if (!shown) return null;

  return (
    <div
      aria-live="polite"
      style={{
        flexShrink: 0,
        padding: '0.4rem 1.5rem',
        borderBottom: '1px solid var(--border-subtle)',
        background: pulsing ? 'var(--accent-muted)' : 'var(--surface)',
        transition: 'background 200ms ease',
        display: 'flex',
        alignItems: 'center',
        gap: '0.45rem',
      }}
    >
      <span style={{ fontSize: '0.7rem', opacity: 0.55, lineHeight: 1 }} aria-hidden>
        🔬
      </span>
      <span
        style={{
          fontFamily: "var(--font-sans, 'DM Sans')",
          fontSize: 12,
          color: 'var(--text-secondary)',
          opacity: visible ? 1 : 0,
          transition: `opacity ${FADE_MS}ms ease`,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {shown}
      </span>
    </div>
  );
}
