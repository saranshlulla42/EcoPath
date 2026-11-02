/**
 * Turning a Stage 4 verdict into what the command bar says.
 *
 * Four outcomes, deliberately distinct. The domain rule is that "this bird does
 * not migrate" and "we don't know whether this bird migrates" are different
 * answers, and a UI that renders both as an empty map has collapsed them. So
 * each carries its own shape, its own wording, and its own evidence.
 */

export type MigrationStatus = 'migratory' | 'resident' | 'insufficient_data';
export type InsufficientBasis = 'coverage' | 'inconclusive' | null;

export interface SpeciesStatus {
  status: MigrationStatus;
  confidence: number;
  insufficient_basis: InsufficientBasis;
  total_records: number;
  months_with_data: number;
  max_displacement_km: number | null;
  reasons?: string;
}

export type MigrationOutcome =
  | { kind: 'track'; status: SpeciesStatus }
  | { kind: 'resident'; status: SpeciesStatus; message: string }
  | { kind: 'insufficient'; status: SpeciesStatus; message: string }
  | { kind: 'inconclusive'; status: SpeciesStatus; message: string }
  | { kind: 'unknown-species'; message: string };

/**
 * What `migration <species>` should render.
 *
 * `null` status means the species was never precomputed, which is not the same
 * as having no migration: it is a gap in our processing, and saying so is the
 * only honest option.
 */
export function migrationOutcome(
  commonName: string,
  status: SpeciesStatus | null,
): MigrationOutcome {
  if (!status) {
    return {
      kind: 'unknown-species',
      message:
        `${commonName} has not been analysed yet — no occurrence data has been ` +
        `precomputed for it, so we cannot say whether it migrates.`,
    };
  }

  if (status.status === 'migratory') {
    return { kind: 'track', status };
  }

  if (status.status === 'resident') {
    const km = status.max_displacement_km ?? 0;
    return {
      kind: 'resident',
      status,
      message:
        `${commonName} is resident — no migratory pattern to show. Its monthly ` +
        `centres of occurrence move only ${Math.round(km)} km across the year, ` +
        `from ${status.total_records.toLocaleString()} records covering ` +
        `${status.months_with_data} months.`,
    };
  }

  if (status.insufficient_basis === 'inconclusive') {
    const km = status.max_displacement_km ?? 0;
    return {
      kind: 'inconclusive',
      status,
      message:
        `The data for ${commonName} is inconclusive. There is plenty of it — ` +
        `${status.total_records.toLocaleString()} records across ` +
        `${status.months_with_data} months — but its centres of occurrence move ` +
        `${Math.round(km)} km, which falls between the resident and migratory ` +
        `cutoffs. We will not guess which side it belongs on.`,
    };
  }

  return {
    kind: 'insufficient',
    status,
    message:
      `Insufficient data for ${commonName} — ` +
      `${status.total_records.toLocaleString()} records, ` +
      `${status.months_with_data} months covered. That is not enough to tell a ` +
      `resident bird from a poorly-recorded migrant, so no status is claimed.`,
  };
}

/** Short label for a chip or badge. */
export function statusLabel(status: SpeciesStatus | null): string {
  if (!status) return 'not analysed';
  if (status.status === 'migratory') return 'migratory';
  if (status.status === 'resident') return 'resident';
  return status.insufficient_basis === 'inconclusive' ? 'inconclusive' : 'insufficient data';
}

/**
 * Evidence line shown beside any status. Never optional: a verdict without its
 * coverage is the thing the domain rules forbid.
 */
export function evidenceLine(status: SpeciesStatus | null): string {
  if (!status) return 'no records processed';
  const parts = [
    `${status.total_records.toLocaleString()} records`,
    `${status.months_with_data}/12 months`,
  ];
  if (status.max_displacement_km != null) {
    parts.push(`${Math.round(status.max_displacement_km)} km seasonal shift`);
  }
  parts.push(`confidence ${(status.confidence * 100).toFixed(0)}%`);
  return parts.join(' · ');
}
