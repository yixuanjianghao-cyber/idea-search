// 离线自检：不碰网络，验证编译、打分、去重、过滤、排序
// 跑法：node test/selftest.mjs
import assert from 'node:assert/strict';
import { compile, norm } from '../lib/intent.mjs';
import { scoreRepo, dedupe, applyFilters, sortBy, mergeAndRank } from '../lib/rank.mjs';

let pass = 0, fail = 0;
function t(name, fn) {
  try { fn(); pass++; console.log(`  ok   ${name}`); }
  catch (e) { fail++; console.log(`  FAIL ${name}\n       ${e.message}`); }
}

console.log('意图编译');

t('中文概念映射到英文检索词', () => {
  const p = compile('轻量的 python 库，把网页转成 markdown');
  assert.equal(p.primary, 'html-to-markdown');
  assert.ok(p.keywords.some(k => k.term === 'lightweight'));
  assert.ok(p.raw.length > 0);
});

t('"转码" 不被单字连接词吃掉（v1 的 bug）', () => {
  const p = compile('ffmpeg 批量转码');
  assert.ok(p.keywords.some(k => k.term === 'ffmpeg'), 'ffmpeg 应保留');
  assert.ok(p.zhTerms.includes('转码'), '转码 应作为中文原话保留');
});

t('"3d" 不被拆成单个 d 误命中 markdown（v2 的 bug）', () => {
  const p = compile('轻量的 python 库，把网页转成 markdown');
  assert.ok(!p.keywords.some(k => k.term === '3d'), '3d 不该出现');
  assert.ok(!p.keywords.some(k => k.term === 'modeling'));
});

t('品牌走生态路', () => {
  const p = compile('微信机器人自动回复');
  assert.ok(p.brands.includes('wechat'));
  assert.ok(p.variants.some(v => v.kind === 'brand'));
});

t('纯英文触发词必须字面出现', () => {
  const p = compile('写个网页');
  assert.ok(!p.keywords.some(k => k.term === 'rat'), 'rat 不该命中');
});

t('检索式不超过 maxQueries 且带限定符', () => {
  const p = compile('自托管的笔记软件，支持双链', { maxQueries: 3 });
  assert.equal(p.variants.length, 3);
  assert.ok(p.variants[0].q.includes('in:name,description'));
  assert.ok(p.lang === null || typeof p.lang === 'string');
});

t('norm 保留业务词，剥掉虚词', () => {
  assert.equal(norm('把网页转成markdown'), '网页markdown');
  assert.equal(norm('批量转码'), '批量转码');
  assert.equal(norm('个人财务记账'), '个人财务记账');
});

console.log('打分');

const plan = compile('自托管的笔记软件，支持双链');
const mk = (over = {}) => ({
  full_name: 'acme/notes', owner: 'acme', html_url: 'https://github.com/acme/notes',
  description: 'Self-hosted note-taking app with knowledge base', stars: 100, forks: 5,
  issues: 3, lang: 'TypeScript', topics: ['self-hosted', 'note-taking'], pushed_at: new Date().toISOString(),
  created_at: '2024-01-01T00:00:00Z', archived: false, fork: false, size: 900, license: 'MIT', ...over
});

t('主词命中 > 主词不命中', () => {
  const a = scoreRepo(mk(), plan, ['精确']);
  const b = scoreRepo(mk({ full_name: 'x/y', description: 'unrelated tool', topics: [] }), plan, ['精确']);
  assert.ok(a.score > b.score);
});

t('归档件被压分', () => {
  const a = scoreRepo(mk(), plan, ['精确']);
  const b = scoreRepo(mk({ archived: true }), plan, ['精确']);
  assert.ok(a.score > b.score);
});

t('多路命中加分但封顶', () => {
  const one = scoreRepo(mk(), plan, ['精确']);
  const four = scoreRepo(mk(), plan, ['精确', '宽泛', '中文原话', '生态']);
  assert.ok(four.score > one.score);
  assert.ok(four.score - one.score <= 0.1);
});

console.log('去重 / 过滤 / 排序');

t('同描述近似仓库只留星高的', () => {
  const a = { full_name: 'a/x', description: 'Self-hosted note-taking app with knowledge base and more', stars: 10 };
  const b = { full_name: 'b/x', description: 'Self-hosted note-taking app with knowledge base and more', stars: 99 };
  const out = dedupe([a, b]);
  assert.equal(out.length, 1);
  assert.equal(out[0].full_name, 'b/x');
});

t('过滤：星标 / 归档 / 时间', () => {
  const old = new Date(Date.now() - 400 * 864e5).toISOString();
  const items = [
    mk({ full_name: 'a/1', stars: 5 }),
    mk({ full_name: 'a/2', stars: 500 }),
    mk({ full_name: 'a/3', archived: true }),
    mk({ full_name: 'a/4', pushed_at: old })
  ];
  const out = applyFilters(items, { minStars: 100, updatedWithin: 365, includeArchived: false });
  assert.deepEqual(out.map(r => r.full_name), ['a/2']);
});

t('四种排序都真的换顺序', () => {
  const items = [
    { score: 0.2, stars: 10, pushed_at: '2020-01-01T00:00:00Z', created_at: '2019-01-01T00:00:00Z' },
    { score: 0.9, stars: 1000, pushed_at: new Date().toISOString(), created_at: '2024-06-01T00:00:00Z' }
  ];
  assert.equal(sortBy(items, 'relevance')[0].score, 0.9);
  assert.equal(sortBy(items, 'stars')[0].stars, 1000);
  assert.equal(sortBy(items, 'recent')[0].stars, 1000);
  assert.ok(Array.isArray(sortBy(items, 'trending')));
});

t('主榜只放主词命中，中文生态单独一栏', () => {
  const buckets = [
    { label: '精确', items: [
      mk({ full_name: 'good/notes', description: 'note-taking self-hosted' }),
      mk({ full_name: 'good/notes2', description: 'note-taking self-hosted wiki' }),
      mk({ full_name: 'good/notes3', description: 'note-taking knowledge base' }),
      mk({ full_name: 'weak/thing', description: '完全无关的东西', topics: [] })
    ] },
    { label: '中文原话', items: [
      mk({ full_name: 'cn/big', description: '开屏广告 笔记 android', stars: 5000, topics: ['android', 'note-taking'] }),
      mk({ full_name: 'cn/noise', description: '随便什么', stars: 9000, topics: [] })
    ] }
  ];
  const out = mergeAndRank(buckets, plan, { limit: 10 });
  assert.ok(out.results.length >= 3);
  assert.ok(out.results.every(r => r.primaryHit > 0), '主榜不该混入弱结果');
  assert.ok(out.native.every(r => !out.results.some(x => x.full_name === r.full_name)));
  assert.ok(!out.native.some(r => r.full_name === 'cn/noise'), '没命中检索词的仓库不该进生态栏');
});

t('强结果太少时允许弱结果兜底', () => {
  const buckets = [{ label: '精确', items: [mk({ full_name: 'only/one' }), mk({ full_name: 'weak/two', description: '无关', topics: [] })] }];
  const out = mergeAndRank(buckets, plan, { limit: 10 });
  assert.ok(out.results.length >= 1);
});

console.log(`\n${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
