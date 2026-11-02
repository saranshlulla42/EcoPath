import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getResolver, resetResolver } from '../lib/taxonomy/load';
import { CATALOGUE_SCI_NAMES, TAXONOMY_FIXTURE } from './fixtures/taxonomy.fixture';

function fakeFetch(body: unknown, ok = true, status = 200) {
  return vi.fn(async () => ({
    ok,
    status,
    json: async () => body,
  })) as unknown as typeof fetch;
}

describe('resolver loading', () => {
  beforeEach(() => resetResolver());

  it('builds a working resolver from a fetched taxonomy', async () => {
    const resolver = await getResolver({
      fetchImpl: fakeFetch(TAXONOMY_FIXTURE),
      catalogueSciNames: CATALOGUE_SCI_NAMES,
    });
    const r = resolver.resolve('Bar-tailed Godwit');
    expect(r.status).toBe('resolved');
    if (r.status === 'resolved') expect(r.taxon.taxonId).toBe('bartgo');
  });

  it('fetches once no matter how many callers ask concurrently', async () => {
    const impl = fakeFetch(TAXONOMY_FIXTURE);
    const [a, b, c] = await Promise.all([
      getResolver({ fetchImpl: impl }),
      getResolver({ fetchImpl: impl }),
      getResolver({ fetchImpl: impl }),
    ]);
    expect(impl).toHaveBeenCalledTimes(1);
    expect(a).toBe(b);
    expect(b).toBe(c);
  });

  it('explains how to generate the artifact when it is missing', async () => {
    await expect(
      getResolver({ fetchImpl: fakeFetch(null, false, 404) }),
    ).rejects.toThrow(/build-taxonomy/);
  });

  it('allows a retry after a failed load rather than caching the failure', async () => {
    await expect(getResolver({ fetchImpl: fakeFetch(null, false, 500) })).rejects.toThrow();
    const resolver = await getResolver({ fetchImpl: fakeFetch(TAXONOMY_FIXTURE) });
    expect(resolver.resolve('House Sparrow').status).toBe('resolved');
  });
});
