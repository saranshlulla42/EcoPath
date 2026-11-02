'use client';

import { useEffect, useState } from 'react';
import { ChartSpec, fetchChartSpec } from '../../../lib/chartService';
import { CONTAINER_STYLE, TITLE_STYLE } from './chart-theme';

/**
 * Renders a chart block whose series live server-side behind a `series_ref`.
 *
 * Blocks that still carry inline `series` bypass this entirely (see
 * BlockRenderer), so older sessions and any model response that inlines data
 * keep working unchanged.
 */
export function ChartRefResolver({
  seriesRef,
  title,
  render,
}: {
  seriesRef: string;
  title?: string;
  render: (spec: ChartSpec) => React.ReactNode;
}) {
  const [spec, setSpec] = useState<ChartSpec | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'missing'>('loading');

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    fetchChartSpec(seriesRef).then(s => {
      if (cancelled) return;
      if (s && s.series?.length) {
        setSpec(s);
        setState('ready');
      } else {
        setState('missing');
      }
    });
    return () => {
      cancelled = true;
    };
  }, [seriesRef]);

  if (state === 'loading') {
    return (
      <div style={CONTAINER_STYLE}>
        {title && <p style={TITLE_STYLE}>{title}</p>}
        <div
          style={{
            height: 280,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: 0.5,
            fontFamily: 'DM Sans',
            fontSize: 13,
          }}
        >
          Loading chart…
        </div>
      </div>
    );
  }

  // The chart expired out of the server-side store (sessions are time-boxed).
  // Say so plainly rather than rendering an empty frame — the narrative above
  // already carries the numbers.
  if (state === 'missing' || !spec) {
    return (
      <div style={CONTAINER_STYLE}>
        {title && <p style={TITLE_STYLE}>{title}</p>}
        <div
          style={{
            height: 120,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: 0.5,
            fontFamily: 'DM Sans',
            fontSize: 13,
            textAlign: 'center',
            padding: '0 24px',
          }}
        >
          This chart is no longer available — ask the question again to regenerate it.
        </div>
      </div>
    );
  }

  return <>{render(spec)}</>;
}
