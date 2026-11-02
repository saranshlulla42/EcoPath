/**
 * Turning a parsed command into an action.
 *
 * Most commands are routed to the existing tab that already renders them: the
 * bar replaces the navigation, not the views. That keeps the old tabs reachable
 * and working while the bar reaches parity, and means this file carries routing
 * rather than a second rendering stack.
 *
 * `migration` is the exception. It cannot navigate blindly, because a resident
 * or under-recorded species must produce a sentence rather than an empty map —
 * so its status is checked first and the answer is inline.
 */

import type { ParseResult, ResolvedSpecies } from './parse';
import { migrationOutcome, type MigrationOutcome, type SpeciesStatus } from './status';

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export type Action =
  /** Send the user to an existing view. */
  | { kind: 'navigate'; href: string; label: string }
  /** Show text in the bar itself. */
  | { kind: 'message'; tone: 'info' | 'warn'; title: string; body: string }
  /** A migration answer, which may be a map or a sentence. */
  | { kind: 'migration'; outcome: MigrationOutcome; species: ResolvedSpecies }
  /** Hand the text to the research agent. */
  | { kind: 'agent'; question: string }
  /** Command help. */
  | { kind: 'help'; verb?: string };

export interface ExecuteResult {
  action: Action;
  /** Whether serving this required any HTTP request. */
  networkCalled: boolean;
  /** Whether the research agent was invoked. */
  llmCalled: boolean;
}

/** Fetch the Stage 4 verdict. `null` means the species was never analysed. */
export async function fetchStatus(scientificName: string): Promise<SpeciesStatus | null> {
  try {
    const resp = await fetch(
      `${BASE}/api/precompute/status?sci=${encodeURIComponent(scientificName)}`,
    );
    if (!resp.ok) return null;
    return (await resp.json()) as SpeciesStatus;
  } catch {
    return null;
  }
}

/**
 * The GBIF key for a resolved taxon.
 *
 * The species route is `/species/[id]` where the id is a GBIF key, not a name —
 * navigating with a scientific name renders "Species not found on GBIF." The
 * lookup is by *exact* scientific name against the catalogue, so the canonical
 * identity established by the resolver is what travels; nothing fuzzy happens
 * here.
 */
export async function gbifKeyFor(scientificName: string): Promise<number | null> {
  try {
    const resp = await fetch(
      `${BASE}/api/data/species/resolve?name=${encodeURIComponent(scientificName)}`,
    );
    if (!resp.ok) return null;
    const body = (await resp.json()) as { data?: { gbif_key?: number; scientific_name?: string } };
    const row = body.data;
    if (!row?.gbif_key) return null;

    // That endpoint resolves names fuzzily. We hand it a canonical scientific
    // name and accept the answer only if it comes back unchanged — otherwise a
    // near-miss upstream could substitute a different bird behind an identity
    // the resolver already settled.
    const returned = (row.scientific_name ?? '').trim().toLowerCase();
    if (returned !== scientificName.trim().toLowerCase()) return null;
    return row.gbif_key;
  } catch {
    return null;
  }
}

function notInCatalogue(s: ResolvedSpecies): ExecuteResult {
  return {
    action: {
      kind: 'message',
      tone: 'warn',
      title: `${s.taxon.commonName} is not in the catalogue`,
      body:
        `The name resolved to ${s.taxon.scientificName}, but EcoPath holds no ` +
        `GBIF record for it, so there is no species page to open.`,
    },
    networkCalled: true,
    llmCalled: false,
  };
}

/** `/species/[id]` keyed by GBIF key. */
async function speciesNav(
  s: ResolvedSpecies,
  suffix = '',
  label?: string,
): Promise<ExecuteResult> {
  const key = await gbifKeyFor(s.taxon.scientificName);
  if (key == null) return notInCatalogue(s);
  return {
    action: {
      kind: 'navigate',
      href: `/species/${key}${suffix}`,
      label: label ?? s.taxon.commonName,
    },
    networkCalled: true,
    llmCalled: false,
  };
}

export async function execute(parsed: ParseResult): Promise<ExecuteResult> {
  if (parsed.kind !== 'command') {
    if (parsed.kind === 'fallback') {
      return { action: { kind: 'agent', question: parsed.text }, networkCalled: true, llmCalled: true };
    }
    return {
      action: { kind: 'message', tone: 'info', title: 'Nothing to run', body: '' },
      networkCalled: false,
      llmCalled: false,
    };
  }

  const { spec, species, values } = parsed;

  if (parsed.unavailable) {
    return {
      action: {
        kind: 'message',
        tone: 'warn',
        title: `${spec.verb} is unavailable`,
        body: parsed.unavailable,
      },
      networkCalled: false,
      llmCalled: false,
    };
  }

  switch (spec.verb) {
    case 'help':
      return {
        action: { kind: 'help', verb: values.command as string | undefined },
        networkCalled: false,
        llmCalled: false,
      };

    case 'migration': {
      const s = species[0];
      const status = await fetchStatus(s.taxon.scientificName);
      return {
        action: { kind: 'migration', outcome: migrationOutcome(s.taxon.commonName, status), species: s },
        networkCalled: true,
        llmCalled: false,
      };
    }

    case 'species':
      return speciesNav(species[0]);

    case 'range': {
      const s = species[0];
      const month = values.month ? `&month=${values.month}` : '';
      return {
        action: {
          kind: 'navigate',
          href: `/maps?sci=${encodeURIComponent(s.taxon.scientificName)}${month}`,
          label: `${s.taxon.commonName} range`,
        },
        networkCalled: true,
        llmCalled: false,
      };
    }

    case 'chart':
      return speciesNav(
        species[0],
        `?view=chart&metric=${values.metric ?? 'observations'}`,
        `${species[0].taxon.commonName} chart`,
      );

    case 'status': {
      const s = species[0];
      const status = await fetchStatus(s.taxon.scientificName);
      return {
        action: { kind: 'migration', outcome: migrationOutcome(s.taxon.commonName, status), species: s },
        networkCalled: true,
        llmCalled: false,
      };
    }

    case 'anomalies':
      return speciesNav(
        species[0],
        '?view=anomalies',
        `${species[0].taxon.commonName} anomalies`,
      );

    case 'compare':
      return {
        action: {
          kind: 'navigate',
          href:
            `/maps?compare=${encodeURIComponent(species[0].taxon.scientificName)}` +
            `,${encodeURIComponent(species[1].taxon.scientificName)}`,
          label: `${species[0].taxon.commonName} vs ${species[1].taxon.commonName}`,
        },
        networkCalled: true,
        llmCalled: false,
      };

    case 'weather':
      return speciesNav(
        species[0],
        `?view=weather&region=${encodeURIComponent(String(values.region ?? ''))}`,
        `${species[0].taxon.commonName} vs weather`,
      );

    case 'region':
      return {
        action: {
          kind: 'navigate',
          href: `/maps?region=${encodeURIComponent(String(values.region ?? ''))}`,
          label: String(values.region ?? ''),
        },
        networkCalled: true,
        llmCalled: false,
      };

    case 'list': {
      const params = new URLSearchParams();
      if (values.iucn) params.set('iucn', String(values.iucn));
      if (values.region) params.set('region', String(values.region));
      return {
        action: { kind: 'navigate', href: `/?${params.toString()}`, label: 'Species list' },
        networkCalled: true,
        llmCalled: false,
      };
    }

    default:
      return {
        action: {
          kind: 'message',
          tone: 'warn',
          title: 'Not wired yet',
          body: `${spec.verb} parses but has no action bound.`,
        },
        networkCalled: false,
        llmCalled: false,
      };
  }
}
