// GitHub's public Trending page is the source of rank and period star gains.
import { readFileSync, writeFileSync, renameSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, dirname } from 'node:path';
import { fetchRead, networkMessage } from './network.mjs';
const FILE = join(process.env.GHF_DATA_DIR || homedir(), '.github-finder-trending.json');
const cache = new Map(), inflight = new Map();
const TTL = 10 * 60 * 1000;
const PERIODS = new Set(['daily', 'weekly', 'monthly']);
try {
  const saved = JSON.parse(readFileSync(FILE, 'utf8'));
  for (const period of PERIODS) {
    const data = saved[period];
    if (data?.period === period && Number.isFinite(data.fetchedAt) && data.fetchedAt <= Date.now() &&
        Array.isArray(data.items) && data.items.length && data.items.length <= 25 &&
        data.items.every(r => /^[\w.-]+\/[\w.-]+$/.test(r.full_name) && r.trending_period === period)) cache.set(period, data);
  }
} catch { /* First run or damaged cache: fetch from GitHub. */ }
function persist() {
  try {
    mkdirSync(dirname(FILE), {recursive:true});
    writeFileSync(FILE + '.tmp', JSON.stringify(Object.fromEntries(cache)), {mode:0o600});
    renameSync(FILE + '.tmp', FILE);
  } catch { /* A read-only disk must not turn a successful sync into an error. */ }
}

function text(html) {
  return String(html || '').replace(/<[^>]+>/g, ' ')
    .replace(/&#(x[0-9a-f]+|\d+);/gi, (_, n) => {
      const code = n[0].toLowerCase() === 'x' ? parseInt(n.slice(1), 16) : Number(n);
      return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : '';
    })
    .replace(/&(?:amp|lt|gt|quot|apos|nbsp);/g, s => ({ '&amp;':'&', '&lt;':'<', '&gt;':'>', '&quot;':'"', '&apos;':"'", '&nbsp;':' ' })[s])
    .replace(/\s+/g, ' ').trim();
}
function number(s) {
  const m = text(s).replace(/,/g, '').match(/([\d.]+)\s*([km])?/i);
  return m ? Math.round(Number(m[1]) * ({ k:1000, m:1000000 }[m[2]?.toLowerCase()] || 1)) : null;
}

export function parseTrending(html, period = 'daily') {
  const expected = { daily:'today', weekly:'this week', monthly:'this month' }[period];
  if (!expected) throw new Error('不支持的排行周期');
  const items = [], seen = new Set();
  for (const match of String(html).matchAll(/<article\b[^>]*class=["'][^"']*\bBox-row\b[^"']*["'][^>]*>([\s\S]*?)<\/article>/gi)) {
    const article = match[1], heading = article.match(/<h2\b[^>]*>([\s\S]*?)<\/h2>/i)?.[1] || '';
    const full = heading.match(/href=["']\/([\w.-]+\/[\w.-]+)["']/i)?.[1];
    if (!full || seen.has(full.toLowerCase())) continue;
    const links = [...article.matchAll(/<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi)];
    const starLink = links.find(m => m[1] === `/${full}/stargazers`);
    const forkLink = links.find(m => m[1] === `/${full}/forks`);
    const gains = article.match(/([\d,.]+)\s+stars?\s+(today|this week|this month)/i);
    if (gains && gains[2].toLowerCase() !== expected) throw new Error('GitHub 返回的星标周期与所选周期不一致');
    seen.add(full.toLowerCase());
    items.push({ full_name:full, owner:full.split('/')[0], html_url:`https://github.com/${full}`,
      description:text(article.match(/<p\b[^>]*>([\s\S]*?)<\/p>/i)?.[1]),
      lang:text(article.match(/itemprop=["']programmingLanguage["'][^>]*>([\s\S]*?)<\//i)?.[1]) || null,
      stars:starLink ? number(starLink[2]) : null, forks:forkLink ? number(forkLink[2]) : null,
      stars_period:gains ? number(gains[1]) : null, trending_rank:items.length + 1, trending_period:period });
    if (items.length >= 25) break;
  }
  if (!items.length) throw new Error('未能读取 GitHub 热度榜，页面可能暂不可用或结构已变化');
  return items;
}

export async function trending(period = 'daily', force = false) {
  if (!PERIODS.has(period)) throw new Error('请选择 daily / weekly / monthly');
  const hit = cache.get(period), now = Date.now();
  if (hit && now - hit.fetchedAt < (force ? 30000 : TTL)) return { ...hit, cached:true, stale:false };
  if (inflight.has(period)) return inflight.get(period);
  const request = (async () => {
    const sourceUrl = `https://github.com/trending?since=${period}`;
    try {
      const response = await fetchRead(sourceUrl, { headers:{ Accept:'text/html', 'User-Agent':'IdeaSearch-local-preview' } }, 25000);
      if (!response.ok) throw new Error(`GitHub 暂不可用（HTTP ${response.status}）`);
      const html = await response.text();
      if (html.length > 3000000) throw new Error('GitHub 返回内容超出限制');
      const data = { items:parseTrending(html, period), period, source:'GitHub Trending', sourceUrl, fetchedAt:Date.now() };
      cache.set(period, data);
      persist();
      return { ...data, cached:false, stale:false };
    } catch (error) {
      if (hit) return { ...hit, cached:true, stale:true, warning:'同步失败，显示上次快照：' + networkMessage(error) };
      throw new Error(networkMessage(error));
    }
  })();
  inflight.set(period, request);
  try { return await request; } finally { inflight.delete(period); }
}
