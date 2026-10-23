// 命令行 v2：node cli.mjs "想法" [--lang Python] [--stars 100] [--sort stars] [--json] [--open]
import { findStream, findCode } from './lib/search.mjs';

const argv = process.argv.slice(2);
const flag = (name, def = '') => {
  const i = argv.findIndex(a => a === `--${name}`);
  if (i < 0) return def;
  const v = argv[i + 1];
  if (v === undefined || v.startsWith('--')) { argv.splice(i, 1); return 'true'; }
  argv.splice(i, 2);
  return v;
};

const lang = flag('lang');
const minStars = Number(flag('stars', '0')) || 0;
const limit = Number(flag('limit', '12')) || 12;
const sortMode = flag('sort', 'relevance');
const updated = Number(flag('updated', '0')) || 0;
const maxQueries = Number(flag('queries', '4')) || 4;
const json = flag('json') === 'true';
const open = flag('open') === 'true';
const mode = flag('mode', 'repo');
const query = argv.join(' ').trim();

if (!query) {
  console.log('用法: node cli.mjs "一句中文想法" [--lang Python] [--stars 100] [--sort stars|recent|trending] [--updated 365] [--queries 2] [--json] [--open] [--mode code]');
  process.exit(0);
}

const t0 = Date.now();
const out = mode === 'code'
  ? await findCode(query, { lang, perPage: limit })
  : await findStream(query, { lang, minStars, updatedWithin: updated, sortMode, limit, maxQueries, perPage: 30 }, e => {
      if (json) return;
      if (e.type === 'bucket') process.stderr.write(`  回 ${e.label} ${e.count} 条（${e.progress.done}/${e.progress.of}）\n`);
      if (e.type === 'bucketError') process.stderr.write(`  ! ${e.label}: ${e.message}\n`);
    });

if (json) {
  console.log(JSON.stringify({ ...out, took: Date.now() - t0 }, null, 2));
  process.exit(0);
}

const p = out.plan || {};
console.log('');
console.log(`主词 ${p.primary || '-'}   语言 ${p.lang || '不限'}   标签 ${(p.topics || []).join(',') || '-'}`);
console.log(`关键词 ${(p.keywords || []).map(k => k.term).join(', ') || '-'}`);
for (const v of p.variants || []) console.log(`  [${v.label}] ${v.q}${v.sort ? '  (' + v.sort + ')' : ''}`);
console.log('');

if (!out.results.length) {
  console.log('没有结果。' + ((out.warnings || [])[0] || ''));
  process.exit(0);
}

const s = out.stats || {};
console.log(`候选 ${s.candidates ?? '-'} → 去重 ${s.afterDedupe ?? '-'} → 过滤 ${s.afterFilter ?? '-'} · ${((Date.now() - t0) / 1000).toFixed(1)}s\n`);

for (const [i, r] of out.results.entries()) {
  if (mode === 'code') {
    console.log(`${i + 1}. ${r.full_name}  ${r.path}\n   ${r.html_url}`);
    continue;
  }
  const h = r.health >= 0.7 ? '健康' : r.health >= 0.4 ? '一般' : '信息少';
  console.log(`${String(i + 1).padStart(2)}. ${r.full_name}   ★${r.stars}  ⑂${r.forks}  ${r.lang || '-'}  ${r.why.recency}  [${h}]`);
  console.log(`    ${(r.description || '(无描述)').slice(0, 100)}`);
  console.log(`    命中 ${(r.why.matched || []).join(' ') || '-'} · 评分 ${r.score}${r.sources.length > 1 ? ' · ' + r.sources.join('+') : ''}`);
  console.log(`    ${r.html_url}\n`);
}

if (out.native && out.native.length) {
  console.log('中文生态（按星标，未参与打分）');
  for (const r of out.native) {
    console.log(`  ${r.full_name}  ★${r.stars}  ${r.lang || '-'}`);
    console.log(`  ${(r.description || '').slice(0, 90)}`);
  }
  console.log('');
}

if (open && out.results[0]) {
  const url = process.platform === 'win32'
    ? `cmd /c start "" "${out.results[0].html_url}"`
    : `xdg-open "${out.results[0].html_url}"`;
  const { exec } = await import('node:child_process');
  exec(url);
}
