/**
 * Resolves chart series that the agent deliberately kept out of the model's
 * context.
 *
 * Tools register their full series server-side and hand the model only a
 * summary plus a `series_ref`. The model quotes that ref in its chart block;
 * this fetches the real points. Bulk data therefore never enters the prompt
 * and never has to be echoed back out in the model's JSON answer.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ChartSeries {
  name: string;
  data: { x: string; y: number }[];
  color?: string;
}

export interface ChartSpec {
  type: string;
  title: string;
  x_label: string;
  y_label: string;
  series: ChartSeries[];
  annotations?: { x: string; label: string }[];
}

// Refs are immutable once minted, so a resolved spec can be cached for the
// lifetime of the page. Keyed in-flight too, so a re-render mid-fetch does not
// fire a second request.
const cache = new Map<string, ChartSpec>();
const inflight = new Map<string, Promise<ChartSpec | null>>();

export async function fetchChartSpec(ref: string): Promise<ChartSpec | null> {
  const hit = cache.get(ref);
  if (hit) return hit;

  const pending = inflight.get(ref);
  if (pending) return pending;

  const p = (async () => {
    try {
      const resp = await fetch(`${BASE}/api/chart/${encodeURIComponent(ref)}`);
      if (!resp.ok) return null;
      const spec = (await resp.json()) as ChartSpec;
      cache.set(ref, spec);
      return spec;
    } catch {
      // An unresolvable ref is not fatal: the caller falls back to the
      // narrative, which already carries the summary the model reasoned over.
      return null;
    } finally {
      inflight.delete(ref);
    }
  })();

  inflight.set(ref, p);
  return p;
}
