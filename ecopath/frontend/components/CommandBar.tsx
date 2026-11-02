'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getResolver } from '../lib/taxonomy/load';
import type { Resolver } from '../lib/taxonomy/resolver';
import { parse, type ParseResult } from '../lib/commands/parse';
import { execute, type Action } from '../lib/commands/execute';
import { COMMANDS } from '../lib/commands/registry';
import { evidenceLine, statusLabel } from '../lib/commands/status';
import * as telemetry from '../lib/commands/telemetry';

const REGIONS = new Set([
  'andhra pradesh', 'arunachal pradesh', 'assam', 'bihar', 'chhattisgarh', 'goa',
  'gujarat', 'haryana', 'himachal pradesh', 'jharkhand', 'karnataka', 'kerala',
  'madhya pradesh', 'maharashtra', 'manipur', 'meghalaya', 'mizoram', 'nagaland',
  'odisha', 'punjab', 'rajasthan', 'sikkim', 'tamil nadu', 'telangana', 'tripura',
  'uttar pradesh', 'uttarakhand', 'west bengal', 'delhi', 'ladakh',
]);

/**
 * The single entry point.
 *
 * Parsing runs on every keystroke and is deliberately cheap — the preview under
 * the input shows what will happen before the user commits, which is what makes
 * a closed command set discoverable rather than something you have to memorise.
 * Nothing leaves the browser until Enter, and for most commands nothing reaches
 * the agent at all.
 */
export function CommandBar() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [resolver, setResolver] = useState<Resolver | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [stats, setStats] = useState(() => telemetry.summary());
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    telemetry.load();
    setStats(telemetry.summary());
    getResolver().then(setResolver).catch(e => setLoadError(String(e?.message ?? e)));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(v => !v);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const parsed: ParseResult | null = useMemo(() => {
    if (!resolver || !input.trim()) return null;
    return parse(input, { resolver, regions: REGIONS });
  }, [input, resolver]);

  const run = useCallback(
    async (override?: string) => {
      if (!resolver) return;
      const text = override ?? input;
      if (!text.trim()) return;

      const t0 = performance.now();
      const result = parse(text, { resolver, regions: REGIONS });
      const parseMs = performance.now() - t0;

      setBusy(true);
      const exec = await execute(result);
      setAction(exec.action);
      setBusy(false);

      telemetry.record({
        input: text,
        outcome:
          result.kind === 'command' ? 'command'
          : result.kind === 'disambiguate' ? 'disambiguate'
          : result.kind === 'fallback' ? 'fallback'
          : 'empty',
        verb: result.kind === 'command' ? result.spec.verb : null,
        llmCalled: exec.llmCalled,
        networkCalled: exec.networkCalled,
        parseMs,
        totalMs: performance.now() - t0,
      });
      setStats(telemetry.summary());

      if (exec.action.kind === 'navigate') {
        router.push(exec.action.href);
        setOpen(false);
      }
    },
    [input, resolver, router],
  );

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 50,
          padding: '10px 16px', borderRadius: 999, border: '1px solid #cfd8cf',
          background: '#fff', fontFamily: 'DM Sans', fontSize: 13, cursor: 'pointer',
          boxShadow: '0 2px 12px rgba(0,0,0,0.12)',
        }}
      >
        Search or run a command &nbsp;<kbd>⌘K</kbd>
      </button>
    );
  }

  return (
    <div
      onClick={() => setOpen(false)}
      style={{
        position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(0,0,0,0.35)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: '12vh',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 'min(680px, 92vw)', background: '#fff', borderRadius: 12,
          boxShadow: '0 16px 48px rgba(0,0,0,0.25)', overflow: 'hidden',
          fontFamily: 'DM Sans',
        }}
      >
        <input
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') void run();
          }}
          placeholder={resolver ? 'migration bar-tailed godwit' : 'Loading taxonomy…'}
          disabled={!resolver}
          style={{
            width: '100%', padding: '18px 20px', fontSize: 17, border: 'none',
            outline: 'none', fontFamily: 'DM Sans',
          }}
        />

        <div style={{ borderTop: '1px solid #eee', maxHeight: '52vh', overflowY: 'auto' }}>
          {loadError && <Row tone="warn">Taxonomy unavailable — {loadError}</Row>}

          {parsed && <Preview parsed={parsed} onPick={name => { setInput(name); void run(name); }} />}

          {!input.trim() && <HelpList />}

          {busy && <Row>Working…</Row>}

          {action && <ActionView action={action} />}
        </div>

        <div
          style={{
            borderTop: '1px solid #eee', padding: '8px 20px', fontSize: 11,
            color: '#667', display: 'flex', justifyContent: 'space-between',
          }}
        >
          <span>{stats}</span>
          <span>esc to close</span>
        </div>
      </div>
    </div>
  );
}

function Row({ children, tone }: { children: React.ReactNode; tone?: 'warn' }) {
  return (
    <div style={{ padding: '12px 20px', fontSize: 13, color: tone === 'warn' ? '#a4442a' : '#334' }}>
      {children}
    </div>
  );
}

/** What will happen on Enter, shown before committing to it. */
function Preview({ parsed, onPick }: { parsed: ParseResult; onPick: (s: string) => void }) {
  if (parsed.kind === 'command') {
    const args = [
      ...parsed.species.map(s => s.taxon.commonName),
      ...Object.entries(parsed.values).map(([k, v]) => `${k}: ${v}`),
    ];
    return (
      <Row>
        <strong>{parsed.spec.verb}</strong>
        {args.length > 0 && <> — {args.join(', ')}</>}
        {parsed.species[0] && parsed.species[0].confidence < 1 && (
          <span style={{ color: '#667' }}>
            {' '}(matched “{parsed.species[0].matchedAlias}”,{' '}
            {(parsed.species[0].confidence * 100).toFixed(0)}%)
          </span>
        )}
        {parsed.unavailable && (
          <div style={{ color: '#a4442a', marginTop: 4 }}>{parsed.unavailable}</div>
        )}
      </Row>
    );
  }

  if (parsed.kind === 'disambiguate') {
    return (
      <div>
        <Row>Which one?</Row>
        {parsed.resolution.candidates.map(c => (
          <button
            key={c.taxon.taxonId}
            onClick={() =>
              onPick(
                parsed.spec ? `${parsed.spec.verb} ${c.taxon.commonName}` : c.taxon.commonName,
              )
            }
            style={{
              display: 'block', width: '100%', textAlign: 'left', padding: '10px 20px',
              border: 'none', background: 'transparent', cursor: 'pointer',
              fontFamily: 'DM Sans', fontSize: 13,
            }}
          >
            <strong>{c.taxon.commonName}</strong>{' '}
            <span style={{ color: '#667' }}>
              {c.taxon.scientificName} · {(c.confidence * 100).toFixed(0)}%
              {c.taxon.inCatalogue === false && ' · no records held'}
            </span>
          </button>
        ))}
      </div>
    );
  }

  if (parsed.kind === 'fallback') {
    return (
      <Row>
        {parsed.reason === 'unresolved-species'
          ? 'No species matches that name.'
          : 'No command matches — Enter asks the research agent.'}
      </Row>
    );
  }
  return null;
}

function ActionView({ action }: { action: Action }) {
  if (action.kind === 'message') {
    return (
      <Row tone={action.tone === 'warn' ? 'warn' : undefined}>
        <strong>{action.title}</strong>
        {action.body && <div style={{ marginTop: 4 }}>{action.body}</div>}
      </Row>
    );
  }

  if (action.kind === 'migration') {
    const o = action.outcome;
    if (o.kind === 'track') {
      return (
        <Row>
          <strong>{action.species.taxon.commonName}</strong> — {statusLabel(o.status)}
          <div style={{ color: '#667', marginTop: 4 }}>{evidenceLine(o.status)}</div>
        </Row>
      );
    }
    const status = 'status' in o ? o.status : null;
    return (
      <Row tone={o.kind === 'insufficient' ? 'warn' : undefined}>
        <strong>{statusLabel(status)}</strong>
        <div style={{ marginTop: 4 }}>{o.message}</div>
        {status && <div style={{ color: '#667', marginTop: 4 }}>{evidenceLine(status)}</div>}
      </Row>
    );
  }

  if (action.kind === 'agent') {
    return <Row>Asked the research agent: “{action.question}”</Row>;
  }

  if (action.kind === 'help') return <HelpList only={action.verb} />;
  return null;
}

function HelpList({ only }: { only?: string }) {
  const list = only ? COMMANDS.filter(c => c.verb === only || c.aliases.includes(only)) : COMMANDS;
  return (
    <div style={{ padding: '8px 0' }}>
      {list.map(c => (
        <div key={c.verb} style={{ padding: '6px 20px', fontSize: 12.5, display: 'flex', gap: 12 }}>
          <code style={{ minWidth: 96, color: '#2f5d3a' }}>{c.verb}</code>
          <span style={{ color: '#334', flex: 1 }}>
            {c.summary}
            <span style={{ color: '#889' }}> — {c.example}</span>
          </span>
        </div>
      ))}
    </div>
  );
}
