// GitHub API 客户端 v2：超时、单飞合并、缓存、配额回传
import { token as readToken } from '../config.mjs';
import { createHash } from 'node:crypto';
import { fetchRead } from './network.mjs';

const API = 'https://api.github.com';
const TTL = 10 * 60 * 1000;
const cache = new Map();
const inflight = new Map();

const gateState = { active: 0, max: 2, gap: 420, last: 0 };
const sleep = ms => new Promise(r => setTimeout(r, ms));

export const quota = {
  limit: null, remaining: null, reset: null, authed: false, at: 0, resource: 'search'
};

async function gate(fn) {
  while (gateState.active >= gateState.max) await sleep(50);
  gateState.active++;
  try {
    const slot = Math.max(Date.now(), gateState.last);
    gateState.last = slot + gateState.gap;
    const wait = slot - Date.now();
    if (wait > 0) await sleep(wait);
    return await fn();
  } finally {
    gateState.active--;
  }
}

function headers() {
  const h = {
    'Accept': 'application/vnd.github+json',
    'User-Agent': 'github-finder/2.0',
    'X-GitHub-Api-Version': '2022-11-28'
  };
  const t = readToken();
  if (t) h.Authorization = `Bearer ${t}`;
  return h;
}

export function tokenPresent() {
  return Boolean(readToken());
}

function noteQuota(res) {
  const lim = res.headers.get('x-ratelimit-limit');
  const rem = res.headers.get('x-ratelimit-remaining');
  const rst = res.headers.get('x-ratelimit-reset');
  if (lim !== null && rem !== null) {
    quota.limit = Number(lim);
    quota.remaining = Number(rem);
    quota.reset = rst ? Number(rst) * 1000 : null;
    quota.at = Date.now();
    quota.authed = tokenPresent();
    quota.resource = res.headers.get('x-ratelimit-resource') || 'API';
  }
}

async function raw(path, attempt = 0, opts = {}) {
  const res = await gate(() => fetchRead(`${API}${path}`, {
    headers: headers(),
  }));
  noteQuota(res);
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* 非 JSON */ }

  if (res.status === 429 || (res.status === 403 && (res.headers.get('x-ratelimit-remaining') === '0' || res.headers.has('retry-after') || /rate limit/i.test(json?.message || '')))) {
    const retryHdr = Number(res.headers.get('retry-after') || 0) * 1000;
    const resetEpoch = Number(res.headers.get('x-ratelimit-reset') || 0) * 1000;
    const untilReset = resetEpoch ? Math.max(0, resetEpoch - Date.now()) : 0;
    const wait = retryHdr || Math.min(untilReset || 20000, 65000);
    if (attempt === 0 && !opts.noWait && wait <= 65000) {
      await sleep(wait + 800);
      return raw(path, attempt + 1, opts);
    }
    const err = new Error(`GitHub 限流${tokenPresent() ? '' : '（未配 token：核心 60 次/小时）'}`);
    err.code = 'RATE_LIMIT';
    err.retryAfter = wait;
    err.resetAt = quota.reset;
    throw err;
  }
  if (res.status === 422) {
    const err = new Error(`检索式不被接受：${json?.message || 'Unprocessable Entity'}`);
    err.code = 'BAD_QUERY';
    throw err;
  }
  if (res.status === 404) {
    const err = new Error(`仓库不存在或私有：${path}`);
    err.code = 'NOT_FOUND';
    throw err;
  }
  if (!res.ok) {
    const err = new Error(`GitHub ${res.status}：${json?.message || res.statusText}`);
    err.code = 'HTTP';
    throw err;
  }
  return json;
}

/** 同一个 path 的并发请求合并成一次 */
function once(key, fn) {
  key = createHash('sha256').update(readToken()).digest('hex').slice(0, 16) + '|' + key;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL) return Promise.resolve({ ...hit.data, cached: true });
  if (inflight.has(key)) return inflight.get(key);
  const p = fn()
    .then(data => {
      for (const [k, v] of cache) if (Date.now() - v.at >= TTL) cache.delete(k);
      if (cache.size >= 200) cache.delete(cache.keys().next().value);
      cache.set(key, { at: Date.now(), data });
      return { ...data, cached: false };
    })
    .finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
}

function slimRepo(r) {
  return {
    id: r.id,
    full_name: r.full_name,
    owner: r.owner?.login || '',
    avatar: r.owner?.avatar_url || '',
    html_url: r.html_url,
    description: r.description || '',
    stars: r.stargazers_count || 0,
    forks: r.forks_count || 0,
    issues: r.open_issues_count || 0,
    watchers: r.watchers_count || 0,
    lang: r.language || null,
    topics: r.topics || [],
    pushed_at: r.pushed_at,
    created_at: r.created_at,
    updated_at: r.updated_at,
    archived: Boolean(r.archived),
    fork: Boolean(r.fork),
    size: r.size || 0,
    license: r.license?.spdx_id && r.license.spdx_id !== 'NOASSERTION' ? r.license.spdx_id : null,
    homepage: r.homepage || '',
    default_branch: r.default_branch || 'main',
    has_pages: Boolean(r.has_pages)
  };
}

export async function searchRepos(q, opts = {}) {
  const perPage = Math.min(Math.max(Number(opts.perPage) || 30, 1), 100);
  const page = Math.max(Number(opts.page) || 1, 1);
  const key = `repo|${q}|${perPage}|${page}|${opts.sort || ''}|${opts.order || ''}`;
  return once(key, async () => {
    const p = new URLSearchParams({ q, per_page: String(perPage), page: String(page) });
    if (opts.sort) { p.set('sort', opts.sort); p.set('order', opts.order || 'desc'); }
    const data = await raw(`/search/repositories?${p}`);
    return {
      total: data.total_count || 0,
      incomplete: Boolean(data.incomplete_results),
      items: (data.items || []).map(slimRepo)
    };
  });
}

export async function searchCode(q, opts = {}) {
  if (!tokenPresent()) {
    const err = new Error('代码搜索需要 token');
    err.code = 'NO_TOKEN';
    throw err;
  }
  const key = `code|${q}|${opts.perPage || 20}`;
  return once(key, async () => {
    const p = new URLSearchParams({ q, per_page: String(Math.min(Number(opts.perPage) || 20, 100)) });
    const data = await raw(`/search/code?${p}`);
    return {
      total: data.total_count || 0,
      items: (data.items || []).map(i => ({
        full_name: i.repository?.full_name || '',
        html_url: i.html_url,
        repo_url: i.repository?.html_url || '',
        path: i.path,
        stars: i.repository?.stargazers_count || 0
      }))
    };
  });
}

export async function repoDetail(full) {
  const key = `detail|${full}`;
  return once(key, async () => {
    const r = await raw(`/repos/${full}`);
    return { detail: slimRepo(r), readme: null };
  });
}

export function cacheStats() {
  return { entries: cache.size, inflight: inflight.size };
}

export { sleep };

/** 给分析模块用的通用 GET（复用限流闸门与缓存语义） */
export async function apiGet(path, opts = {}) {
  // Wrap arrays as a value so the shared object cache preserves directory lists.
  return (await once(`api|${path}`, async () => ({value:await raw(path, 0, opts)}))).value;
}
