// 编排 v2：编译 → 并发多路检索 → 边到边推 → 合并去重打分
import { compile, suggest } from './intent.mjs';
import { searchRepos, searchCode } from './github.mjs';
import { scoreRepo, mergeAndRank } from './rank.mjs';

function decorate(plan, items, label) {
  return items.map(it => {
    const s = scoreRepo(it, plan, [label]);
    return { ...it, score: s.score, primaryHit: s.primaryHit, health: s.health, why: s.why, sources: [label] };
  });
}

/** 主入口：返回完整结果 */
export async function find(rawQuery, opts = {}) {
  const events = [];
  const out = await findStream(rawQuery, opts, e => events.push(e));
  return { ...out, events };
}

/** 流式入口：每路结果回来就 emit */
export async function findStream(rawQuery, opts = {}, emit = () => {}) {
  const plan = compile(rawQuery, {
    maxQueries: opts.maxQueries,
    lang: opts.lang,
    queries: opts.queries
  });

  emit({ type: 'plan', plan: publicPlan(plan) });
  if (!plan.variants.length) {
    emit({ type: 'done', plan: publicPlan(plan), results: [], stats: { candidates: 0 }, warnings: ['这句话里没解析出可检索的词'] });
    return { plan: publicPlan(plan), results: [], stats: {}, warnings: ['这句话里没解析出可检索的词'] };
  }

  const buckets = [];
  const warnings = [];
  if (plan.required?.length) warnings.push(`需确认的能力：${plan.required.join('、')}；搜索命中不代表能力已验证。`);
  let done = 0;

  await Promise.all(plan.variants.map(async v => {
    try {
      const r = await searchRepos(v.q, { perPage: opts.perPage || 30, sort: v.sort, page: opts.page || 1 });
      const items = decorate(plan, r.items, v.label);
      buckets.push({ label: v.label, kind: v.kind, items: r.items, total: r.total });
      done++;
      emit({
        type: 'bucket',
        label: v.label,
        kind: v.kind,
        q: v.q,
        total: r.total,
        count: items.length,
        cached: r.cached,
        progress: { done, of: plan.variants.length },
        items
      });
    } catch (e) {
      done++;
      warnings.push(`「${v.label}」失败：${e.message}`);
      emit({ type: 'bucketError', label: v.label, kind: v.kind, q: v.q, message: e.message, code: e.code || 'ERR', progress: { done, of: plan.variants.length } });
    }
  }));

  const merged = mergeAndRank(buckets, plan, {
    ...opts,
    sortMode: opts.sortMode || 'relevance',
    minStars: opts.minStars,
    updatedWithin: opts.updatedWithin,
    includeArchived: opts.includeArchived,
    license: opts.license
  });

  const payload = {
    plan: publicPlan(plan),
    results: merged.results,
    native: merged.native || [],
    stats: { ...merged.stats, buckets: buckets.map(b => ({ label: b.label, count: b.items.length, total: b.total })) },
    warnings
  };
  emit({ type: 'done', ...payload });
  return payload;
}

function publicPlan(plan) {
  return {
    raw: plan.raw,
    primary: plan.primary,
    keywords: plan.keywords.map(k => ({ term: k.term, role: k.role, from: k.src })),
    zhTerms: plan.zhTerms,
    brands: plan.brands,
    lang: plan.lang,
    topics: plan.topics,
    excluded: plan.excluded || [],
    required: plan.required || [],
    variants: plan.variants
  };
}

export async function findCode(rawQuery, opts = {}) {
  const plan = compile(rawQuery, { maxQueries: 1, lang: opts.lang });
  const terms = plan.keywords.map(k => k.term).slice(0, 4);
  const q = `${terms.join(' ')}${opts.lang ? ` language:${opts.lang}` : ''}`.trim();
  if (!terms.length) return { plan: publicPlan(plan), results: [], stats: {}, warnings: ['没解析出检索词'] };
  const r = await searchCode(q, { perPage: Number(opts.perPage) || 20 });
  return { plan: publicPlan(plan), results: r.items, stats: { total: r.total }, warnings: [] };
}

export { compile, suggest };
