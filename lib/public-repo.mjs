// Read public repository files when the REST core quota is exhausted.
// Web content is data only: executable plans still come from our templates.
import { fetchRead } from './network.mjs';

async function readText(url, limit = 5000000) {
  const res = await fetchRead(url, {headers:{Accept:'text/html,text/plain', 'User-Agent':'IdeaSearch'}}, 18000);
  if (!res.ok) throw new Error(`公开仓库读取失败（HTTP ${res.status}）`);
  if (Number(res.headers.get('content-length')) > limit) { await res.body?.cancel(); throw new Error('仓库文件超出读取限制'); }
  const reader = res.body.getReader(), chunks = [];
  let size = 0;
  try {
    while (true) {
      const {value,done} = await reader.read(); if (done) break;
      size += value.length;
      if (size > limit) { await reader.cancel(); throw new Error('仓库文件超出读取限制'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  return Buffer.concat(chunks).toString('utf8');
}

export function parsePublicRepo(html, full) {
  if (!/^[\w.-]+\/[\w.-]+$/.test(full)) throw new Error('仓库名称无效');
  let payload;
  for (const script of html.matchAll(/<script\b[^>]*data-target=["']react-app\.embeddedData["'][^>]*>([\s\S]*?)<\/script>/g)) {
    try { const data=JSON.parse(script[1]).payload; if (data?.codeViewRepoRoute && data?.codeViewLayoutRoute) {payload=data;break;} } catch { /* Other embedded widgets. */ }
  }
  const route=payload?.codeViewRepoRoute, meta=payload?.codeViewLayoutRoute?.repo;
  if (!meta || meta.private || !meta.public || `${meta.ownerLogin}/${meta.name}`.toLowerCase() !== full.toLowerCase() || route.path !== '/')
    throw new Error('未能验证公开仓库目录，请配置 GitHub Token 后重试');
  const revision=route.refInfo?.currentOid;
  if (!/^[a-f0-9]{40,64}$/i.test(revision || '')) throw new Error('未能确认仓库版本');
  if (!Array.isArray(route.tree?.items) || route.tree.totalCount > route.tree.items.length) throw new Error('公开目录不完整，请配置 GitHub Token 后重试');
  const entries=route.tree.items.filter(e=>e.path === e.name && !/[\\/\x00-\x1f]/.test(e.name) && !['.','..'].includes(e.name))
    .map(e=>({name:e.name,type:e.contentType === 'directory' ? 'dir' : e.contentType === 'file' ? 'file' : 'unknown'}));
  const about=payload.sidebarAbout || {};
  return {revision, entries, repo:{name:meta.name, full_name:`${meta.ownerLogin}/${meta.name}`, html_url:`https://github.com/${meta.ownerLogin}/${meta.name}`,
    description:about.description || '', topics:(about.topics || []).map(t=>t.name).filter(Boolean),
    stargazers_count:about.stargazerCount ?? 0, forks_count:about.forksCount ?? 0,
    license:about.repo?.license?.spdxId ? {spdx_id:about.repo.license.spdxId} : null,
    archived:!!meta.isArchived, default_branch:meta.defaultBranch, created_at:meta.createdAt,
    homepage:about.website || '', publicFallback:true}};
}

export async function publicRepo(full) {
  const data=parsePublicRepo(await readText(`https://github.com/${full}`), full);
  const files=new Map();
  async function file(name) {
    if (!data.entries.some(e=>e.name === name && e.type === 'file')) throw new Error('目录中未找到此文件');
    if (!files.has(name)) files.set(name,readText(`https://raw.githubusercontent.com/${full}/${data.revision}/${encodeURIComponent(name)}`,1000000));
    return {content:Buffer.from(await files.get(name)).toString('base64')};
  }
  return {async get(path) {
    if (path === `/repos/${full}`) return data.repo;
    if (path === `/repos/${full}/contents/`) return data.entries;
    if (path === `/repos/${full}/readme`) {
      const name=data.entries.find(e=>e.type==='file' && /^readme(?:\.(?:md|rst|txt|markdown))?$/i.test(e.name))?.name;
      if (!name) throw new Error('未找到 README');
      return file(name);
    }
    const prefix=`/repos/${full}/contents/`;
    if (path.startsWith(prefix)) return file(path.slice(prefix.length));
    throw new Error('此信息需 GitHub API 配额，当前仅使用公开文件');
  }};
}
