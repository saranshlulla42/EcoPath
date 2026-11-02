export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  blocks: Block[];
  isStreaming: boolean;
  /**
   * Out-of-band status shown above the blocks — currently only the session
   * expiry warning. Not agent output, so it is rendered separately.
   */
  notice?: string;
}

export type Block =
  | NarrativeBlock
  | LineChartBlock
  | BarChartBlock
  | StatCardBlock
  | ComparisonTableBlock
  | MapHighlightBlock
  | MigrationMapBlock
  | FollowUpsBlock;

export interface NarrativeBlock {
  type: 'narrative';
  content: string;
  isStreaming: boolean;
}

export interface LineChartBlock {
  type: 'line_chart';
  title: string;
  x_label: string;
  y_label: string;
  // Either the points are inline, or `series_ref` names a server-side spec the
  // frontend resolves. Refs keep bulk data out of the model's context in both
  // directions; inline series stay supported for older sessions.
  series?: {
    name: string;
    data: { x: string; y: number }[];
    color?: string;
  }[];
  series_ref?: string;
  annotations?: { x: string; label: string }[];
}

export interface BarChartBlock {
  type: 'bar_chart';
  title: string;
  x_label: string;
  y_label: string;
  series?: {
    name: string;
    data: { x: string; y: number }[];
    color?: string;
  }[];
  series_ref?: string;
}

export interface StatCardBlock {
  type: 'stat_card';
  stats: {
    label: string;
    value: string;
    detail?: string;
  }[];
}

export interface ComparisonTableBlock {
  type: 'comparison_table';
  title: string;
  headers: string[];
  rows: string[][];
}

export interface MapHighlightRegion {
  /** ISO 3166-2 subdivision code, with or without the "IN-" prefix. */
  code: string;
  name: string;
  /** Raw data value behind the highlight — observation count, percentage, etc. */
  value?: number;
  /** Pre-formatted label, shown on the map and in the tooltip. */
  label?: string;
  /** 0–1, how strongly to colour this region relative to its siblings. */
  intensity?: number;
}

export interface MapHighlightBlock {
  type: 'map_highlight';
  title: string;
  /** [longitude, latitude] the map opens on, before auto-fit adjusts it. */
  center?: [number, number];
  zoom?: number;
  regions: MapHighlightRegion[];
  gradient?: 'decline' | 'growth' | 'neutral' | 'comparison';
  species?: string;
  year?: number;
  narrative?: string;
}

export interface MigrationRoute {
  name?: string;
  season?: string;
  /** Flat [longitude, latitude] pairs; the LineString is built client-side. */
  coordinates: [number, number][];
  color?: string;
}

export interface MigrationStopover {
  name: string;
  lat: number;
  lng: number;
  notes?: string;
  /** Position along the route, 1-based. Drives the staggered fade-in. */
  order?: number;
}

export interface MigrationMapBlock {
  type: 'migration_map';
  title?: string;
  species: string;
  center?: [number, number];
  zoom?: number;
  routes: MigrationRoute[];
  stopovers?: MigrationStopover[];
}

export interface FollowUpsBlock {
  type: 'follow_ups';
  suggestions: string[];
}

/**
 * The agent's current research focus, pushed once per response on the
 * `session_state` SSE event. Drives the context indicator bar.
 */
export interface SessionState {
  species: string | null;
  species_scientific: string | null;
  regions: string[];
  year_range: [number, number];
  turn_count: number;
}
