import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after } from 'node:test';
const folder = mkdtempSync(join(tmpdir(), 'idea-trending-'));
process.env.GHF_DATA_DIR = folder;
after(() => rmSync(folder, {recursive:true, force:true}));
const { parseTrending, trending } = await import('../lib/trending.mjs');

const page = (period = 'daily') => `<html><article class="Box-row">
  <a href="/sponsors/someone">Sponsor</a>
  <h2><a href="/example/project"><span>example /</span>project</a></h2>
  <p>A &amp; B &lt;example&gt; &#x4E2D;</p>
  <span itemprop="programmingLanguage">Python</span>
  <a href="/example/project/stargazers"><svg><path d="123"/></svg>12,345</a>
  <a href="/example/project/forks">678</a>
  <span class="float-sm-right">1,234 stars ${{daily:'today',weekly:'this week',monthly:'this month'}[period]}</span>
</article></html>`;

test('Trending parser preserves GitHub rank, total stars, period gains and plain metadata', () => {
  const rows = parseTrending(page());
  assert.equal(rows[0].full_name, 'example/project');
  assert.equal(rows[0].stars, 12345);
  assert.equal(rows[0].stars_period, 1234);
  assert.equal(rows[0].trending_rank, 1);
  assert.equal(rows[0].lang, 'Python');
  assert.match(rows[0].description, /A & B <example> 中/);
});
test('wrong periods, changed pages and login pages never become empty successful charts', () => {
  assert.throws(() => parseTrending(page('weekly'), 'daily'), /周期/);
  assert.throws(() => parseTrending('<html>Please login</html>'), /未能读取/);
});
test('missing metric stays unknown rather than a fabricated zero', () => {
  const [row] = parseTrending('<article class="Box-row"><h2><a href="/a/b">a/b</a></h2></article>');
  assert.equal(row.stars_period, null); assert.equal(row.stars, null);
});
test('periods use separate bounded caches; manual refresh cooldown and stale fallback work', async () => {
  const originalFetch = globalThis.fetch, originalNow = Date.now;
  let now=originalNow(), calls=0, fail=false;
  Date.now=()=>now;
  globalThis.fetch=async url => {
    calls++;
    assert.match(url, /^https:\/\/github\.com\/trending\?since=(daily|weekly|monthly)$/);
    if (fail) throw new Error('offline');
    return new Response(page(new URL(url).searchParams.get('since')), {status:200});
  };
  try {
    for (const period of ['daily','weekly','monthly']) assert.equal((await trending(period)).period,period);
    assert.equal(calls,3);
    assert.equal((await trending('daily')).cached,true);
    assert.equal((await trending('daily',true)).cached,true);
    now+=31000; await trending('daily',true); assert.equal(calls,4);
    now+=650000; fail=true;
    const stale=await trending('daily'); assert.equal(stale.stale,true); assert.match(stale.warning,/同步失败/);
    assert.equal(stale.items[0].stars_period,1234);
    const restarted = await import('../lib/trending.mjs?restart');
    const restored = await restarted.trending('weekly');
    assert.equal(restored.stale, true);
    assert.equal(restored.items[0].trending_period, 'weekly');
    assert.equal(restored.items[0].stars_period, 1234);
    await assert.rejects(trending('yearly'),/请选择/);
  } finally { globalThis.fetch=originalFetch; Date.now=originalNow; }
});
