import { test } from 'node:test';
import assert from 'node:assert/strict';
import { discover } from '../lib/discover.mjs';

test('discovery uses one bounded GitHub request and returns real mapped metadata', async () => {
  const original = globalThis.fetch;
  let count = 0;
  globalThis.fetch = async url => {
    count++;
    const parsed = new URL(url);
    assert.equal(parsed.searchParams.get('page'), '5');
    assert.equal(parsed.searchParams.get('per_page'), '30');
    assert.match(parsed.searchParams.get('q'), /developer-tools/);
    assert.match(parsed.searchParams.get('q'), /archived:false/);
    return new Response(JSON.stringify({ total_count: 1, items: [{ full_name: 'test/project', stargazers_count: 12 }] }));
  };
  try {
    const result = await discover(null, 999);
    assert.equal(count, 1);
    assert.equal(result.items[0].stars, 12);
    assert.equal(result.items[0].full_name, 'test/project');
  } finally { globalThis.fetch = original; }
});
