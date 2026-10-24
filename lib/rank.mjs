// 打分与排序 v2：主词门控 + 覆盖 + 热度 + 新鲜度 + 健康度，附排序模式与近似去重

const MONTH = 1000 * 60 * 60 * 24 * 30;
const YEAR = 365 * 24 * 3600 * 1000;

function indexRepo(repo) {
  const nameParts = String(repo.full_name).toLowerCase().split(/[/._-]+/);
  return {
    name: new Set(nameParts),
    desc: (repo.description || '').toLowerCase(),
    topics: new Set((repo.topics || []).map(t => t.toLowerCase()))
  };
}

const inName = (ix, t) => ix.name.has(t) || [...ix.name].some(x => x.includes(t));
const inDesc = (ix, t) => ix.desc.includes(t);
const inTopic = (ix, t) => [...ix.topics].some(x => x.includes(t) || t.includes(x));

function health(repo) {
  let h = 0;
  if (repo.license) h += 0.30;
  if ((repo.description || '').length > 30) h += 0.15;
  if ((repo.topics || []).length >= 3) h += 0.15;
  const ratio = repo.stars > 0 ? repo.issues / repo.stars : 0;
  if (repo.stars >= 50 && ratio >= 0.005 && ratio <= 0.20) h += 0.25;   // 有互动但没堆成山
  if (repo.size > 50) h += 0.15;
  return Math.min(h, 1);
}

export function scoreRepo(repo, plan, srcLabels = []) {
  const ix = indexRepo(repo);
  const kws = plan.keywords.map(k => k.term).filter(Boolean);
  const primary = plan.primary || kws[0] || '';
  const alts = [primary, ...(plan.zhTerms || [])].filter(Boolean);

  let primaryHit = 0, bestTerm = primary;
  for (const term of alts) {
    let h = 0;
    if (inName(ix, term)) h = 1;
    else if (inDesc(ix, term)) h = 0.7;
    else if (inTopic(ix, term)) h = 0.5;
    if (h > primaryHit) { primaryHit = h; bestTerm = term; }
  }

  const srcOf = new Map(plan.keywords.map(k => [k.term, k.src]));
  const secondaries = kws.filter(k => k !== primary);
  const hitTerms = primaryHit > 0 ? [bestTerm] : [];
  let secRaw = 0;
  const conceptSec = [];
  for (const t of secondaries) {
    const nameOrDesc = inName(ix, t) || inDesc(ix, t);
    const topic = inTopic(ix, t);
    if (nameOrDesc) { secRaw += 1; hitTerms.push(t); }
    else if (topic) { secRaw += 0.6; hitTerms.push(t); }
    if ((nameOrDesc || topic) && srcOf.get(t) === 'concept') conceptSec.push(t);
  }
  const secCov = secondaries.length ? Math.min(secRaw / secondaries.length, 1) : 0;

  const planTopics = (plan.topics || []).map(t => t.toLowerCase());
  const topicHit = planTopics.filter(t => inTopic(ix, t)).length;
  const topicScore = planTopics.length ? Math.min(topicHit / planTopics.length, 1) : 0;

  const langMatch = plan.lang && repo.lang && plan.lang.toLowerCase() === String(repo.lang).toLowerCase() ? 1 : 0;
  const starScore = Math.min(Math.log10(1 + repo.stars) / 6, 1);
  const monthsOld = Math.max(0, (Date.now() - new Date(repo.pushed_at || repo.updated_at || Date.now()).getTime()) / MONTH);
  const recency = Math.exp(-monthsOld / 24);
  const hp = health(repo);
  const ecosystemText = `${repo.full_name} ${ix.desc} ${(repo.topics || []).join(' ')}`.toLowerCase().replace(/[-_]+/g, ' ');
  const ecosystemHits = (plan.brands || []).filter(term => {
    const normalized = term.toLowerCase().replace(/[-_]+/g, ' ');
    const escaped = normalized.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`).test(ecosystemText);
  });

  // 相关度优先：星标只做加成，不能盖过“它对不对题”
  let score =
    0.32 * primaryHit +
    0.20 * secCov +
    0.08 * topicScore +
    0.03 * langMatch +
    0.17 * starScore +
    0.08 * recency +
    0.08 * hp;

  // 描述里出现完整主词短语，说明作者自己就是这么叫它的
  if (primaryHit > 0 && primary.length >= 4 && ix.desc.includes(primary)) score += 0.04;

  // 中文原话直接命中：这是最强的意图信号（「破甲」「开屏广告」这种词，
  // 作者自己在描述里写出来，基本就是你要的那类项目）
  const zhHit = (plan.zhTerms || []).some(t => t && (ix.desc.includes(t) || inName(ix, t)));
  if (zhHit) score += 0.08;

  // 指定宿主生态时，用匹配证据提升相关插件，避免通用高星项目盖过它们。
  if (plan.brands?.length) {
    if (ecosystemHits.length) score += 0.20;
    else score *= 0.65;
  }

  if (repo.archived) score -= 0.25;
  if (repo.fork) score -= 0.05;
  if (!repo.description) score -= 0.05;
  if (repo.stars < 3 && repo.size < 40) score -= 0.06;

  // 多路都捞到 = 强信号，但封顶，别让一个小仓库靠重复出现刷分
  const multi = Math.min((srcLabels.length - 1) * 0.03, 0.09);
  score += multi;

  // 主词没中但次词中了两个以上，不算噪声，只轻压
  if (primaryHit === 0) score *= 0.72;

  return {
    score: Number(score.toFixed(4)),
    primaryHit,
    secCov: Number(secCov.toFixed(2)),
    health: Number(hp.toFixed(2)),
    monthsOld,
    why: {
      matched: hitTerms.slice(0, 8),
      primary: bestTerm,
      primaryHit,
      topicHits: planTopics.filter(t => inTopic(ix, t)),
      ecosystemHits,
      recency: monthsOld <= 1 ? '一个月内更新' : monthsOld <= 6 ? `${Math.round(monthsOld)} 个月前更新` : `${Math.round(monthsOld / 12)} 年前更新`,
      health: hp >= 0.7 ? '健康' : hp >= 0.4 ? '一般' : '信息少'
    }
  };
}

/** 近似去重：描述归一后相同 + 名字相似度高 → 只留 star 高的那个（就地替换，不留残影） */
export function dedupe(items) {
  const sig = new Map();
  const out = [];
  for (const r of items) {
    const d = (r.description || '').toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '').slice(0, 48);
    const nameKey = String(r.full_name).toLowerCase().split('/')[1] || '';
    const key = d.length >= 20 ? `d:${nameKey}:${d}` : `repo:${String(r.full_name).toLowerCase()}`;
    const idx = sig.get(key);
    if (idx !== undefined) {
      const prev = out[idx];
      if (r.stars > prev.stars) {
        r.mergedFrom = [prev.full_name, ...(prev.mergedFrom || [])];
        out[idx] = r;
      }
      continue;
    }
    sig.set(key, out.length);
    out.push(r);
  }
  return out;
}

export function applyFilters(items, f = {}) {
  const minStars = Number(f.minStars) || 0;
  const days = Number(f.updatedWithin) || 0;
  const cutoff = days ? Date.now() - days * 864e5 : 0;
  return items.filter(r => {
    if (r.stars < minStars) return false;
    if (cutoff && new Date(r.pushed_at || 0).getTime() < cutoff) return false;
    if (!f.includeArchived && r.archived) return false;
    if (f.lang && String(r.lang || '').toLowerCase() !== String(f.lang).toLowerCase()) return false;
    if (f.license && !r.license) return false;
    return true;
  });
}

export function sortBy(items, mode) {
  const a = [...items];
  switch (mode) {
    case 'stars': return a.sort((x, y) => y.stars - x.stars);
    case 'recent': return a.sort((x, y) => new Date(y.pushed_at || 0) - new Date(x.pushed_at || 0));
    case 'trending': return a.sort((x, y) => {
      const ax = x.stars / Math.max((Date.now() - new Date(x.created_at || 0)) / YEAR, 0.4);
      const ay = y.stars / Math.max((Date.now() - new Date(y.created_at || 0)) / YEAR, 0.4);
      return ay - ax;
    });
    default: return a.sort((x, y) => y.score - x.score);
  }
}

export function mergeAndRank(buckets, plan, opts = {}) {
  const byName = new Map();
  for (const b of buckets) {
    for (const repo of b.items) {
      const cur = byName.get(repo.full_name);
      if (cur) { cur.sources.push(b.label); continue; }
      byName.set(repo.full_name, { repo, sources: [b.label] });
    }
  }
  let scored = [];
  for (const { repo, sources } of byName.values()) {
    const s = scoreRepo(repo, plan, sources);
    // 主词命中，或者至少两个检索词命中，才算“对题”；其余是词库蹭出来的噪声
    const strongEnough = plan.fallback || s.primaryHit > 0 || (s.why.matched || []).length >= 2;
    if (!strongEnough) continue;
    const text = `${repo.full_name} ${repo.description || ''} ${(repo.topics || []).join(' ')}`.toLowerCase();
    if ((plan.excluded || []).some(t => new RegExp(`(^|[^a-z0-9])${t}([^a-z0-9]|$)`, 'i').test(text))) continue;
    s.why.unverified = (plan.required || []).filter(t => !text.includes(t) && !(t === 'backlinks' && /backlink|双链|双向链接/.test(text)));
    scored.push({ ...repo, score: s.score, primaryHit: s.primaryHit, health: s.health, why: s.why, sources });
  }

  scored = dedupe(scored);
  const beforeFilter = scored.length;
  scored = applyFilters(scored, opts);

  const strong = scored.filter(r => r.primaryHit > 0);
  const pool = scored;

  const sorted = sortBy(pool, opts.sortMode || 'relevance');
  const limit = Math.min(Math.max(Number(opts.limit) || 30, 1), 100);
  const results = sorted.slice(0, limit);

  // 中文生态栏：来自"中文原话"检索、且主榜里没有的，按星标排。
  // 这一栏专门给只有中文描述的项目（gkd / SKIP 这类），不参与打分，避免蹭词噪声。
  const taken = new Set(results.map(r => r.full_name));
  const nativeSource = buckets.find(b => b.label === '中文原话');
  const native = nativeSource
    ? applyFilters([...nativeSource.items], opts)
        .filter(r => !taken.has(r.full_name) && !r.archived)
        .map(r => {
          const s = scoreRepo(r, plan, ['中文原话']);
          return { ...r, score: s.score, why: s.why, sources: ['中文原话'], _hit: s.why.matched.length };
        })
        // GitHub 对中文分词很糙，"开屏广告"会命中一堆只在 readme 里提过"广告"的仓库。
        // 这一栏只留至少命中一个检索词的，其余丢掉。
        .filter(r => r._hit >= 2)
        .sort((a, b) => b.stars - a.stars)
        .slice(0, 8)
        .map(({ _hit, ...r }) => r)
    : [];

  return {
    results,
    native,
    stats: {
      candidates: byName.size,
      afterDedupe: beforeFilter,
      afterFilter: scored.length,
      kept: results.length,
      strong: strong.length,
      native: native.length
    }
  };
}

