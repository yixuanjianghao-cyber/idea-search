// 服务 v2：静态页 + JSON API + SSE 流式 + token 配置
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join, extname, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { findStream, findCode, suggest } from './lib/search.mjs';
import { analyzeRepo } from './lib/analyze.mjs';
import { discover } from './lib/discover.mjs';
import { trending } from './lib/trending.mjs';
import { fetchRead } from './lib/network.mjs';
import { quota, tokenPresent, cacheStats } from './lib/github.mjs';
import { load, save, maskedToken, token as readToken, configPath } from './config.mjs';

const ROOT = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT) || 7788;
const HOST = process.env.HOST || '127.0.0.1';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.map': 'application/json; charset=utf-8'
};

const BASE_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Cache-Control': 'no-store'
};

function send(res, code, body, type = 'application/json; charset=utf-8') {
  res.writeHead(code, { ...BASE_HEADERS, 'Content-Type': type });
  res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

function readBody(req, limit = 8192) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', c => {
      size += c.length;
      if (size > limit) { reject(new Error('body too large')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

function parseOpts(url) {
  const g = k => url.searchParams.get(k) || '';
  const num = k => Number(g(k)) || 0;
  return {
    lang: g('lang'),
    minStars: num('minStars'),
    updatedWithin: num('updated'),
    sortMode: g('sort') || 'relevance',
    limit: num('limit') || 30,
    perPage: num('perPage') || 30,
    page: num('page') || 1,
    includeArchived: g('archived') === '1',
    license: g('license') === '1',
    maxQueries: num('maxQueries') || 4,
    queries: g('extra') ? g('extra').split(';').map(s => s.trim()).filter(Boolean) : undefined
  };
}

const server = createServer(async (req, res) => {
  let url;
  try { url = new URL(req.url, `http://${req.headers.host || 'localhost'}`); }
  catch { return send(res, 400, { error: 'bad url' }); }

  if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) return send(res, 403, { error: 'invalid host' });
  const origin = req.headers.origin;
  if (origin && origin !== `http://${req.headers.host}`) return send(res, 403, { error: 'invalid origin' });
  if (req.method === 'POST' && !String(req.headers['content-type'] || '').startsWith('application/json')) return send(res, 415, { error: 'JSON required' });
  try {
    if (url.pathname === '/api/check-github-token' && req.method === 'POST') {
      const body = JSON.parse(await readBody(req));
      const candidate = body.useSaved ? readToken() : typeof body.token === 'string' ? body.token.trim() : '';
      if (candidate.startsWith('sk-')) return send(res, 400, {error:'这是 AI API Key，请在 AI 设置中填写。这里需要 GitHub Token。'});
      const headers = { Accept:'application/vnd.github+json', 'User-Agent':'IdeaSearch' };
      if (candidate) headers.Authorization = `Bearer ${candidate}`;
      const response = await fetchRead('https://api.github.com/rate_limit', {headers}, 12000);
      if (!response.ok) return send(res, response.status === 401 ? 401 : 502, {error:response.status === 401 ? 'GitHub Token 无效或已过期。' : 'GitHub 暂时无法连接，请稍后重试。'});
      const data = await response.json();
      return send(res, 200, {ok:true, authenticated:!!candidate, remaining:data.resources?.core?.remaining});
    }
    if (url.pathname === '/api/trending') {
      if (req.method !== 'GET') return send(res, 405, { error:'method not allowed' });
      const period = url.searchParams.get('period') || 'daily';
      if (!['daily','weekly','monthly'].includes(period)) return send(res, 400, { error:'无效的排行周期' });
      return send(res, 200, await trending(period, url.searchParams.get('refresh') === '1'));
    }
    if (url.pathname === '/api/discover') {
      return send(res, 200, await discover(url.searchParams.get('q'), url.searchParams.get('page')));
    }
    if (url.pathname === '/api/health') {
      return send(res, 200, {
        ok: true, app: 'idea-search', version: '2.8.1',
        token: tokenPresent(),
        tokenMasked: maskedToken(),
        configPath,
        quota: { ...quota, fresh: Date.now() - quota.at < 60000 ? { limit: quota.limit, remaining: quota.remaining } : null },
        cache: cacheStats()
      });
    }

    if (url.pathname === '/api/config') {
      if (req.method === 'GET') {
        return send(res, 200, { path: configPath, token: maskedToken(), hasToken: tokenPresent(), lang: load().lang || '', sort: load().sort || '' });
      }
      if (req.method === 'POST') {
        const body = await readBody(req);
        const j = JSON.parse(body || '{}');
        const patch = {};
        if (typeof j.token === 'string') {
          if (j.token.trim().startsWith('sk-')) return send(res, 400, {error:'DeepSeek 等 AI Key 请填到 AI 设置，不要填到 GitHub Token。'});
          patch.token = j.token.trim();
        }
        if (typeof j.lang === 'string') patch.lang = j.lang.trim();
        if (typeof j.sort === 'string') patch.sort = j.sort.trim();
        save(patch);
        return send(res, 200, { ok: true, token: maskedToken(), hasToken: tokenPresent() });
      }
      return send(res, 405, { error: 'method not allowed' });
    }


    if (url.pathname === '/api/analyze/stream') {
      const repo = (url.searchParams.get('repo') || '').trim();
      const q = url.searchParams.get('q') || '';
      res.writeHead(200, {
        ...BASE_HEADERS,
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
      });
      const ev = obj => { if (!res.writableEnded) res.write(`data: ${JSON.stringify(obj)}\n\n`); };
      if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) { ev({ type: 'error', message: 'repo 参数要 owner/name' }); return res.end(); }
      try {
        const data = await analyzeRepo(repo, q, stage => ev({ type: 'stage', name: stage }));
        ev({ type: 'done', data });
      } catch (e) {
        ev({ type: 'error', message: e.message, code: e.code || 'ERR', resetAt: e.resetAt || null });
      } finally {
        if (!res.writableEnded) res.end();
      }
      return;
    }

    if (url.pathname === '/api/analyze') {
      const repo = (url.searchParams.get('repo') || '').trim();
      if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) return send(res, 400, { error: 'repo 参数要 owner/name' });
      const q = url.searchParams.get('q') || '';
      try {
        const data = await analyzeRepo(repo, q);
        return send(res, 200, data);
      } catch (e) {
        const code = e.code === 'RATE_LIMIT' ? 429 : e.code === 'NOT_FOUND' ? 404 : 502;
        return send(res, code, { error: e.message, code: e.code || 'ERR' });
      }
    }

    if (url.pathname === '/api/suggest') {
      return send(res, 200, { items: suggest(url.searchParams.get('q') || '', 10) });
    }

    if (url.pathname === '/api/search') {
      const q = (url.searchParams.get('q') || '').trim();
      if (!q) return send(res, 400, { error: '缺 q' });
      const opts = parseOpts(url);
      const t0 = Date.now();
      const out = url.searchParams.get('mode') === 'code'
        ? await findCode(q, opts)
        : await findStream(q, opts, () => {});
      return send(res, 200, { ...out, took: Date.now() - t0 });
    }

    if (url.pathname === '/api/stream') {
      const q = (url.searchParams.get('q') || '').trim();
      res.writeHead(200, {
        ...BASE_HEADERS,
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
      });
      const sendEv = obj => { if (!res.writableEnded) res.write(`data: ${JSON.stringify(obj)}\n\n`); };
      if (!q) { sendEv({ type: 'error', message: '缺 q' }); return res.end(); }

      const keep = setInterval(() => { if (!res.writableEnded) res.write(': ping\n\n'); }, 15000);
      let closed = false;
      req.on('close', () => { closed = true; clearInterval(keep); });

      const t0 = Date.now();
      try {
        const out = await findStream(q, parseOpts(url), e => { if (!closed) sendEv(e); });
        sendEv({ type: 'meta', took: Date.now() - t0, total: out.stats?.candidates || 0 });
      } catch (e) {
        sendEv({ type: 'error', message: e.message, code: e.code || 'ERR' });
      } finally {
        clearInterval(keep);
        if (!res.writableEnded) res.end();
      }
      return;
    }

    // 静态
    let p = url.pathname === '/' ? '/index.html' : decodeURIComponent(url.pathname);
    if (p.includes('..')) return send(res, 403, 'no', 'text/plain');
    try {
      const file = await readFile(join(ROOT, 'public', p));
      return send(res, 200, file, MIME[extname(p)] || 'application/octet-stream');
    } catch {
      return send(res, 404, 'not found', 'text/plain; charset=utf-8');
    }
  } catch (e) {
    if (!res.headersSent) return send(res, 500, { error: e.message });
    try { res.end(); } catch { /* 已断开 */ }
  }
});

server.on('clientError', (err, socket) => {
  if (socket.writable) socket.end('HTTP/1.1 400 Bad Request\r\n\r\n');
});

server.listen(PORT, HOST, () => {
  const t = readToken();
  console.log(`Idea Search 2.8.1  http://${HOST}:${PORT}`);
  console.log(`token: ${t ? '已配置 ' + maskedToken() : '未配置（10 次/分，代码搜索不可用）'}`);
  console.log(`配置: ${configPath}`);
});
