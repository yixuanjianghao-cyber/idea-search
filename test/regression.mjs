import { test } from 'node:test';
import assert from 'node:assert/strict';
import { compile } from '../lib/intent.mjs';
import { dedupe, applyFilters, mergeAndRank } from '../lib/rank.mjs';
import { find } from '../lib/search.mjs';
import { usageSteps, deployScript } from '../lib/deployment.mjs';

test('English word boundaries survive; text search is not TypeScript', () => {
  const p = compile('fast full text search');
  assert.equal(p.lang, null);
  assert.ok(p.keywords.some(k => k.term === 'search'));
  assert.ok(!p.keywords.some(k => k.term === 'fastfulltextsearch'));
  assert.equal(compile('rust full text search').lang, 'Rust');
  assert.equal(compile('javascript parser').lang, 'JavaScript');
});
test('negative Docker intent is not a positive requirement', () => {
  const p = compile('不要 Docker 的笔记软件');
  assert.deepEqual(p.excluded, ['docker']);
  assert.ok(!p.keywords.some(k => k.term === 'docker'));
  assert.ok(p.variants.every(v => v.q.includes('NOT docker')));
});
test('manual language overrides detected language before retrieval', () => {
  const p = compile('python 网页转 markdown', { lang: 'Rust' });
  assert.equal(p.lang, 'Rust');
  assert.ok(p.variants.some(v => v.q.includes('language:Rust')));
  assert.ok(p.variants.every(v => !v.q.includes('language:Python')));
});

test('DSH desktop pet intent retains its purpose and prioritizes scoped bilingual queries', () => {
  for (const query of ['dsh桌宠插件', 'DSH 桌面宠物', 'DeepSeek Harness 桌宠插件']) {
    const p = compile(query);
    assert.equal(p.primary, 'pet');
    assert.ok(p.brands.includes('dsh'));
    assert.ok(p.variants[0].q.includes('dsh pet'));
    assert.ok(p.variants.some(v => /dsh 桌宠|dsh 桌面宠物/.test(v.q)));
    assert.ok(p.variants.some(v => v.q.includes('deepseek-harness pet')));
    assert.ok(p.variants.every(v => !v.q.includes('stars:>20')));
    assert.ok(p.variants.length <= 4);
  }
  assert.equal(compile('桌宠').primary, 'pet');
  assert.deepEqual(compile('桌宠').brands, []);
  assert.deepEqual(compile('mydshboard 桌宠').brands, []);
});

test('native pet recall has no hidden star floor and preserves requested constraints', () => {
  const p = compile('最新高星 python 桌宠');
  const native = p.variants.find(v => v.kind === 'native');
  assert.ok(native);
  assert.match(native.q, /language:Python/);
  assert.ok(!compile('桌宠').variants.some(v => /stars:/.test(v.q)));
  const scoped = compile('DSH 桌宠', { lang: 'TypeScript', maxQueries: 2 });
  assert.equal(scoped.variants.length, 2);
  assert.ok(scoped.variants.every(v => v.q.includes('language:TypeScript')));
});

test('low-star ecosystem pets rank above popular generic pets and unrelated DSH plugins', () => {
  const p = compile('dsh桌宠插件');
  const base = { topics: [], size: 80, issues: 0, license: 'MIT', lang: 'JavaScript', pushed_at: new Date().toISOString() };
  const pet = { ...base, full_name: 'example/dsh-dpet', description: 'DSH 的 2D/3D 智能桌宠插件', stars: 1 };
  const generic = { ...base, full_name: 'other/desktop-pet', description: 'Popular virtual desktop pet application', stars: 200000, topics: ['desktop-pet', 'virtual-pet', 'desktop'] };
  const unrelated = { ...base, full_name: 'other/dsh-plugin', description: 'DSH plugin for databases and SQL', stars: 200000 };
  const result = mergeAndRank([{ label: '生态', items: [generic, unrelated, pet] }], p);
  assert.equal(result.results[0].full_name, pet.full_name);
  assert.deepEqual(result.results[0].why.ecosystemHits, ['dsh']);
  assert.ok(!mergeAndRank([{ label: '生态', items: [pet] }], p, { minStars: 20 }).results.length);
});

test('end-to-end DSH pet retrieval asks for pet candidates instead of only generic plugins', async () => {
  const original = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async url => {
    const q = new URL(url).searchParams.get('q');
    seen.push(q);
    const specific = /dsh pet|dsh 桌宠|deepseek-harness pet/.test(q);
    const items = specific ? [{ full_name: 'fixture/dsh-pet', description: 'DSH 桌宠插件', stargazers_count: 2, size: 80 }] : [];
    return new Response(JSON.stringify({ total_count: items.length, items }));
  };
  try {
    const result = await find('dsh桌宠插件');
    assert.equal(result.results[0].full_name, 'fixture/dsh-pet');
    assert.ok(seen.some(q => q.includes('dsh pet')));
    assert.ok(seen.every(q => !q.includes('stars:>20')));
  } finally { globalThis.fetch = original; }
});
test('backlink requirement is retained explicitly', () => {
  const p = compile('自托管的笔记软件，支持双链');
  assert.deepEqual(p.required, ['backlinks']);
  assert.ok(p.variants[0].q.includes('backlinks'));
});
test('unknown ideas preserve custom queries and GitHub README-only candidates', () => {
  const p = compile('羽毛球计分工具', { queries: ['badminton scoreboard'] });
  assert.equal(p.variants[0].q, 'badminton scoreboard');
  const repo = { full_name: 'a/scoreboard', description: 'Badminton scoreboard', topics: [], stars: 20, size: 50, issues: 0 };
  assert.equal(mergeAndRank([{ label: '自定义', items: [repo] }], p).results.length, 1);
});

test('a recognized language cannot swallow an unknown Chinese purpose', () => {
  const p = compile('python 羽毛球计分工具');
  assert.equal(p.lang, 'Python');
  assert.ok(p.fallback);
  assert.ok(p.variants[0].q.includes('羽毛球计分'));
  assert.ok(p.variants.every(v => v.q.includes('language:Python')));
  const repo = { full_name: 'fixture/scoreboard', description: 'Badminton scoreboard', topics: [], stars: 2, size: 80, issues: 0, lang: 'Python' };
  assert.equal(mergeAndRank([{ label: '原话直搜', items: [repo] }], p, { lang: 'Python' }).results.length, 1);
});

test('unknown Chinese details survive known ecosystems and partial concept matches', () => {
  for (const query of ['dsh 捏脸插件', 'dsh 桌宠捏脸插件']) {
    const p = compile(query, { maxQueries: 2, lang: 'TypeScript' });
    assert.ok(p.unmappedTerms.includes('捏脸'));
    assert.ok(p.variants[0].q.includes('dsh'));
    assert.ok(p.variants[0].q.includes('捏脸'));
    assert.ok(p.variants.every(v => v.q.includes('language:TypeScript')));
    assert.ok(p.variants.length <= 2);
  }
});

test('mixed-language fallback returns README candidates and explains original-word retrieval', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async url => {
    const q = new URL(url).searchParams.get('q');
    assert.ok(q.includes('羽毛球计分'));
    assert.ok(q.includes('language:Python'));
    return new Response(JSON.stringify({total_count: 1, items: [{full_name: 'fixture/readme-scoreboard', description: 'Sports scoreboard', language: 'Python', stargazers_count: 1, size: 80}]}));
  };
  try {
    const result = await find('python 羽毛球计分工具', { lang: 'Python' });
    assert.equal(result.results[0].full_name, 'fixture/readme-scoreboard');
    assert.ok(result.warnings.some(w => w.includes('已保留原词检索') && w.includes('羽毛球计分')));
    assert.ok(result.plan.unmappedTerms.includes('羽毛球计分'));
  } finally { globalThis.fetch = original; }
});
test('unrelated repositories with empty descriptions are retained', () => {
  assert.equal(dedupe([{ full_name: 'a/server', stars: 1 }, { full_name: 'b/server', stars: 20 }]).length, 2);
});
test('language filter excludes unknown language', () => {
  assert.equal(applyFilters([{ lang: null }], { lang: 'Rust' }).length, 0);
});
const repo = { name: 'demo', full_name: 'a/demo', html_url: 'https://github.com/a/demo', size: 10 };
test('pyproject installs the package using virtualenv Python without activation', () => {
  const { commands } = usageSteps('python', repo, null, ['pyproject.toml']);
  assert.ok(commands.includes('.venv\\Scripts\\python.exe -m pip install .'));
  assert.ok(!commands.some(c => /requirements|activate/.test(c)));
});
test('Node builds before starting and respects lockfile', () => {
  const { commands } = usageSteps('node-start', repo, { scripts: { start: 'node dist/main.js', build: 'tsc' } }, ['package-lock.json']);
  assert.ok(commands.indexOf('npm run build') < commands.indexOf('npm start'));
  assert.ok(commands.includes('npm ci'));
  const script = deployScript(repo, 'node-start', commands);
  assert.match(script, /call npm ci\r\nif errorlevel 1 exit \/b 1/);
  assert.match(script, /if exist "%TARGET%"/);
  assert.doesNotMatch(script, /pause/);
});
test('unsupported package manager and unknown entry produce no guessed executable plan', () => {
  assert.equal(usageSteps('node-start', repo, { packageManager: 'pnpm@10', scripts: {} }, []).commands.length, 0);
  assert.equal(usageSteps('docker', repo, null, ['Dockerfile']).commands.length, 0);
  assert.equal(deployScript(repo, 'clone', []), '');
});
