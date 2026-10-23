import { test } from 'node:test';
import assert from 'node:assert/strict';
import { compile } from '../lib/intent.mjs';
import { dedupe, applyFilters, mergeAndRank } from '../lib/rank.mjs';
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
