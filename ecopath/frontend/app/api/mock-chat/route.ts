import type { NextRequest } from 'next/server';
import type { Block } from '../../../types/chat';

/**
 * Mock SSE endpoint for developing the chat blocks without the Python agent.
 *
 * Point the chat at it by setting NEXT_PUBLIC_CHAT_MOCK=1. The scenario is
 * chosen from keywords in the last user message — see SCENARIOS below.
 */

export const dynamic = 'force-dynamic';

const NARRATIVE =
  'Across the western states the picture is consistent: **Gujarat** carries the ' +
  'steepest loss at 70% below its five-year mean, with Rajasthan close behind at 38%. ' +
  'Madhya Pradesh is comparatively stable.';

const MAP_A: Block = {
  type: 'map_highlight',
  title: 'Indian Vulture Decline — Western India (2023)',
  center: [73.5, 24.5],
  zoom: 5.5,
  regions: [
    { code: 'GJ', name: 'Gujarat', value: 87, label: '87 obs (↓ 70%)', intensity: 0.9 },
    { code: 'RJ', name: 'Rajasthan', value: 214, label: '214 obs (↓ 38%)', intensity: 0.55 },
    { code: 'MP', name: 'Madhya Pradesh', value: 156, label: '156 obs (↓ 12%)', intensity: 0.2 },
  ],
  gradient: 'decline',
  narrative:
    'Gujarat shows the steepest decline at 70% below the 5-year average, with Rajasthan following at 38%.',
};

const MAP_B: Block = {
  type: 'migration_map',
  title: 'Amur Falcon Autumn Migration',
  species: 'Amur Falcon',
  center: [90.0, 30.0],
  zoom: 3.5,
  routes: [
    {
      name: 'East Asia → India Flyway',
      season: 'autumn',
      coordinates: [
        [116.4, 39.9], [110.0, 35.0], [100.5, 30.2], [95.3, 28.1],
        [94.1, 25.7], [91.0, 23.5], [88.4, 22.3], [85.0, 20.5],
      ],
      color: '#34d399',
    },
  ],
  stopovers: [
    { name: 'Beijing staging area', lat: 39.9, lng: 116.4, notes: 'Pre-migration fattening grounds', order: 1 },
    { name: 'Nagaland roosting site', lat: 25.7, lng: 94.1, notes: 'Largest known roosting — over 1 million birds', order: 2 },
    { name: 'Bay of Bengal crossing', lat: 20.5, lng: 85.0, notes: 'Open water crossing to wintering grounds', order: 3 },
  ],
};

const LINE_CHART: Block = {
  type: 'line_chart',
  title: 'Indian Vulture observations, 2014–2023',
  x_label: 'Year',
  y_label: 'Observations',
  series: [
    {
      name: 'Gujarat',
      data: [
        { x: '2014', y: 342 }, { x: '2015', y: 318 }, { x: '2016', y: 423 },
        { x: '2017', y: 390 }, { x: '2018', y: 301 }, { x: '2019', y: 288 },
        { x: '2020', y: 205 }, { x: '2021', y: 166 }, { x: '2022', y: 124 },
        { x: '2023', y: 87 },
      ],
    },
    {
      name: 'Rajasthan',
      data: [
        { x: '2014', y: 512 }, { x: '2015', y: 498 }, { x: '2016', y: 545 },
        { x: '2017', y: 501 }, { x: '2018', y: 470 }, { x: '2019', y: 402 },
        { x: '2020', y: 366 }, { x: '2021', y: 298 }, { x: '2022', y: 251 },
        { x: '2023', y: 214 },
      ],
    },
  ],
};

const FOLLOW_UPS: Block = {
  type: 'follow_ups',
  suggestions: [
    'Show me the Amur Falcon migration route',
    'Compare this with the White-rumped Vulture',
    'What does the growth gradient look like?',
  ],
};

/** Recolour MAP_A to exercise each gradient mode. */
function gradientVariant(gradient: 'growth' | 'neutral' | 'comparison'): Block {
  if (gradient === 'comparison') {
    return {
      ...(MAP_A as Extract<Block, { type: 'map_highlight' }>),
      title: 'Wintering vs. breeding range',
      gradient: 'comparison',
      regions: [
        { code: 'GJ', name: 'Gujarat', value: 87, label: 'Wintering', intensity: 0.9 },
        { code: 'RJ', name: 'Rajasthan', value: 214, label: 'Breeding', intensity: 0.5 },
      ],
      narrative: 'Two distinct categories, not a severity ramp — each gets its own hue.',
    };
  }
  return {
    ...(MAP_A as Extract<Block, { type: 'map_highlight' }>),
    title: gradient === 'growth' ? 'Population recovery (2023)' : 'Survey coverage (2023)',
    gradient,
    narrative: `Gradient mode: ${gradient}.`,
  };
}

const SINGLE_STATE: Block = {
  type: 'map_highlight',
  title: 'Kerala — Nilgiri Flycatcher records (2023)',
  center: [76.5, 10.5],
  zoom: 4,          // deliberately too wide; auto-fit should tighten it
  regions: [{ code: 'KL', name: 'Kerala', value: 1240, label: '1,240 obs', intensity: 0.8 }],
  gradient: 'growth',
  narrative: 'A single small state — the map should frame Kerala, not all of India.',
};

const WIDE_SPREAD: Block = {
  type: 'map_highlight',
  title: 'Sarus Crane range (2023)',
  center: [78.9, 22.5],
  zoom: 6,          // deliberately too tight; auto-fit should widen it
  regions: [
    { code: 'GJ', name: 'Gujarat', value: 210, label: '210 obs', intensity: 0.5 },
    { code: 'RJ', name: 'Rajasthan', value: 180, label: '180 obs', intensity: 0.4 },
    { code: 'UP', name: 'Uttar Pradesh', value: 640, label: '640 obs', intensity: 0.95 },
    { code: 'AS', name: 'Assam', value: 90, label: '90 obs', intensity: 0.25 },
    { code: 'TN', name: 'Tamil Nadu', value: 60, label: '60 obs', intensity: 0.2 },
    { code: 'KL', name: 'Kerala', value: 45, label: '45 obs', intensity: 0.15 },
    { code: 'WB', name: 'West Bengal', value: 130, label: '130 obs', intensity: 0.35 },
  ],
  gradient: 'neutral',
  narrative: 'Seven states spread across India — auto-fit should zoom out to hold them all.',
};

/** Every shape the renderer must survive without crashing. */
const DEGENERATE: Block[] = [
  { type: 'map_highlight', title: 'No regions at all', center: [78.9, 22.5], zoom: 4, regions: [], gradient: 'decline', narrative: 'Empty regions array — a plain map, no highlights.' },
  { type: 'map_highlight', title: 'Unknown region code', center: [78.9, 22.5], zoom: 4, regions: [{ code: 'XX', name: 'Nowhere', value: 1, label: 'unknown', intensity: 0.9 }], gradient: 'decline', narrative: 'Code XX matches no feature — skipped silently.' },
  { type: 'migration_map', title: 'Two-coordinate route', species: 'Test Species', center: [80, 22], zoom: 4, routes: [{ name: 'Straight line', coordinates: [[72, 19], [88, 22]], color: '#60a5fa' }], stopovers: [] },
  { type: 'migration_map', title: 'Null Island route', species: 'Test Species', center: [0, 0], zoom: 2, routes: [{ name: 'Bad coords', coordinates: [[0, 0], [1, 1]] }], stopovers: [{ name: 'Null Island', lat: 0, lng: 0, notes: 'Middle of the ocean', order: 1 }] },
];

type Scenario = {
  match: RegExp;
  blocks: Block[];
  narrative?: string;
  /** Mock research focus, echoed back on the `session_state` event. */
  session?: { species: string; species_scientific: string; regions: string[] };
};

const DEFAULT_SESSION = {
  species: 'Indian Vulture',
  species_scientific: 'Gyps indicus',
  regions: ['GJ', 'RJ', 'MP'],
};

const SCENARIOS: Scenario[] = [
  { match: /migration|amur|falcon|flyway/i, blocks: [MAP_B, FOLLOW_UPS], narrative: 'The **Amur Falcon** makes one of the longest raptor migrations on record, staging in East Asia before funnelling through Nagaland.', session: { species: 'Amur Falcon', species_scientific: 'Falco amurensis', regions: ['NL'] } },
  { match: /growth/i, blocks: [gradientVariant('growth'), FOLLOW_UPS] },
  { match: /neutral/i, blocks: [gradientVariant('neutral'), FOLLOW_UPS] },
  { match: /comparison/i, blocks: [gradientVariant('comparison'), FOLLOW_UPS] },
  { match: /kerala|single/i, blocks: [SINGLE_STATE, FOLLOW_UPS], session: { species: 'Indian Vulture', species_scientific: 'Gyps indicus', regions: ['KL'] } },
  { match: /wide|spread|sarus|all india/i, blocks: [WIDE_SPREAD, FOLLOW_UPS] },
  { match: /edge|degenerate|broken/i, blocks: [...DEGENERATE, FOLLOW_UPS], narrative: 'Degenerate inputs — none of these should crash the renderer.' },
  // Mock C: a map and a chart in the same message.
  { match: /.*/, blocks: [MAP_A, LINE_CHART, FOLLOW_UPS] },
];

function sse(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

export async function POST(req: NextRequest) {
  let lastUserText = '';
  let turnCount = 1;
  try {
    const body = await req.json();
    const msgs = Array.isArray(body?.messages) ? body.messages : [];
    const userMsgs = msgs.filter((m: { role: string }) => m.role === 'user');
    lastUserText = userMsgs.pop()?.content ?? '';
    turnCount = userMsgs.length + 1;
  } catch {
    // an unparseable body just falls through to the default scenario
  }

  const scenario = SCENARIOS.find((s) => s.match.test(lastUserText)) ?? SCENARIOS[SCENARIOS.length - 1];
  const narrative = scenario.narrative ?? NARRATIVE;
  const sessionState = {
    ...(scenario.session ?? DEFAULT_SESSION),
    year_range: [2014, 2024] as [number, number],
    turn_count: turnCount,
  };

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => controller.enqueue(encoder.encode(sse(event, data)));
      const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

      await wait(400);   // stand in for the agent's thinking pause

      send('block_start', { type: 'narrative' });
      for (const word of narrative.split(' ')) {
        send('text_delta', { content: word + ' ' });
        await wait(28);
      }
      send('block_end', {});

      for (const block of scenario.blocks) {
        await wait(320);
        send('block', block);
      }

      send('session_state', sessionState);
      send('done', {});
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}
