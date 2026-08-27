/**
 * Shared configuration for the inline chat maps.
 *
 * These maps are deliberately *not* the dashboard maps (app/maps/page.tsx,
 * components/migration/MapCanvas.tsx). They are small, read-mostly and exist to
 * support a narrative inside a conversation. They share only the base style URL
 * with the dashboard.
 */

/** Same style the heatmap page uses, so chat and dashboard read as one product. */
export const MAP_STYLE =
  process.env.NEXT_PUBLIC_MAP_STYLE || 'https://tiles.openfreemap.org/styles/dark';

/** State boundaries, generated from Natural Earth admin-1 (see public/geojson/). */
export const BOUNDARY_URL = '/geojson/india-states.geojson';

/** The GeoJSON property that carries the 2-letter subdivision code. */
export const REGION_CODE_PROPERTY = 'state_code';

export const CHAT_MAP_HEIGHT = 280;
export const CHAT_MAP_MOBILE_HEIGHT = 220;
/** Chat maps drop to the shorter height below this viewport width. */
export const MOBILE_BREAKPOINT = 640;

/**
 * Interaction settings. Scroll zoom is off so the map never swallows a scroll
 * gesture aimed at the conversation; the keyboard belongs to the chat input.
 */
export const MAP_INTERACTION = {
  scrollZoom: false,
  dragPan: true,
  dragRotate: false,
  touchZoomRotate: true,
  doubleClickZoom: true,
  keyboard: false,
} as const;

export type GradientKind = 'decline' | 'growth' | 'neutral' | 'comparison';

interface GradientRamp {
  low: string;
  high: string;
  outline: string;
}

export const GRADIENT_COLORS: Record<'decline' | 'growth' | 'neutral', GradientRamp> = {
  decline: {
    low: 'rgba(252, 165, 165, 0.25)',
    high: 'rgba(220, 38, 38, 0.7)',
    outline: 'rgba(220, 38, 38, 0.5)',
  },
  growth: {
    low: 'rgba(134, 239, 172, 0.25)',
    high: 'rgba(22, 163, 74, 0.7)',
    outline: 'rgba(22, 163, 74, 0.5)',
  },
  neutral: {
    low: 'rgba(147, 197, 253, 0.25)',
    high: 'rgba(59, 130, 246, 0.7)',
    outline: 'rgba(59, 130, 246, 0.5)',
  },
};

/** Comparison mode assigns distinct hues rather than a ramp. */
export const COMPARISON_COLORS = [
  { fill: 'rgba(45, 212, 191, 0.5)', outline: 'rgba(45, 212, 191, 0.7)' },   // teal
  { fill: 'rgba(251, 191, 36, 0.5)', outline: 'rgba(251, 191, 36, 0.7)' },   // amber
];

export const ROUTE_COLORS = {
  default: '#34d399',
  glow: 'rgba(52, 211, 153, 0.3)',
};

/** Distinct colours when a migration block carries several flyways. */
export const MULTI_ROUTE_COLORS = ['#34d399', '#60a5fa', '#f472b6'];

/** Target opacity of the highlighted-region fill once it has faded in. */
export const HIGHLIGHT_FILL_OPACITY = 0.85;

const RGBA = /rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)/;

/**
 * Linear interpolation between two rgba() strings.
 *
 * MapLibre expressions can't interpolate colours against a per-feature value,
 * so each region's colour is resolved here in JS and baked into a `case`
 * expression instead.
 */
export function interpolateColor(from: string, to: string, t: number): string {
  const a = RGBA.exec(from);
  const b = RGBA.exec(to);
  if (!a || !b) return to;

  const clamped = Math.max(0, Math.min(1, Number.isFinite(t) ? t : 0));
  const lerp = (x: number, y: number) => x + (y - x) * clamped;

  const r = Math.round(lerp(+a[1], +b[1]));
  const g = Math.round(lerp(+a[2], +b[2]));
  const bl = Math.round(lerp(+a[3], +b[3]));
  const alpha = lerp(a[4] === undefined ? 1 : +a[4], b[4] === undefined ? 1 : +b[4]);

  return `rgba(${r}, ${g}, ${bl}, ${Math.round(alpha * 1000) / 1000})`;
}

/** Outline colour for a gradient mode (comparison outlines are per-region). */
export function getOutlineColor(gradient: GradientKind | undefined): string {
  if (gradient === 'comparison') return COMPARISON_COLORS[0].outline;
  return (GRADIENT_COLORS[gradient as 'decline'] ?? GRADIENT_COLORS.neutral).outline;
}
