import { searchRepos } from './github.mjs';

export async function discover(raw = 'developer-tools', page = 1) {
  // A single bounded API request; shared GitHub client supplies cache/rate limits.
  const term = String(raw || 'developer-tools').trim().slice(0, 100).replace(/[^a-zA-Z0-9+#. -]/g, ' ').trim() || 'developer-tools';
  const q = `${term} in:name,description stars:>30 archived:false`;
  const result = await searchRepos(q, { perPage: 30, page: Math.min(5, Math.max(1, Number(page) || 1)), sort: 'stars' });
  return { items: result.items, total: result.total, cached: result.cached, query: term, fetchedAt: Date.now() };
}
