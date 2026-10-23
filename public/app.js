/* github-finder v2 前端 */
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

const state = {
  q: '',
  plan: null,
  items: new Map(),
  native: [],
  buckets: 0,
  of: 0,
  selected: -1,
  es: null,
  done: false,
  customQueries: null,
  warnings: []
};

const HKEY = 'gf.history.v2';
const FKEY = 'gf.favs.v2';
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = n => n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'k' : String(n);
const ago = iso => {
  const d = (Date.now() - new Date(iso || 0).getTime()) / 864e5;
  if (!iso || d < 0) return '—';
  if (d < 1) return '今天';
  if (d < 30) return `${Math.round(d)} 天前`;
  if (d < 365) return `${Math.round(d / 30)} 个月前`;
  return `${Math.round(d / 365)} 年前`;
};
const toast = msg => {
  const t = $('#toast');
  t.textContent = msg; t.classList.add('on');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove('on'), 1600);
};

/* ── 配额 / 配置 ─────────────────────────── */
async function refreshHealth() {
  try {
    const j = await (await fetch('/api/health')).json();
    const b = $('#quotaBadge');
    const q = j.quota || {};
    if (j.token) {
      b.className = 'badge';
      b.innerHTML = `已认证 <b>${esc(j.tokenMasked || '')}</b>${q.remaining != null ? ` · 剩 ${q.remaining}/${q.limit}` : ''}`;
    } else {
      b.className = 'badge bad';
      b.innerHTML = `未认证 <b>${q.remaining != null ? `${q.remaining}/${q.limit}` : '10 次/分'}</b>`;
    }
    $('#cfgPath').textContent = j.configPath || '~/.github-finder.json';
  } catch { /* 忽略 */ }
}

/* ── 联想 ────────────────────────────────── */
let sugTimer = null;
$('#q').addEventListener('input', e => {
  const v = e.target.value.trim();
  clearTimeout(sugTimer);
  if (v.length < 1) { $('#suggest').hidden = true; return; }
  sugTimer = setTimeout(async () => {
    try {
      const j = await (await fetch('/api/suggest?q=' + encodeURIComponent(v))).json();
      const box = $('#suggest');
      if (!j.items || !j.items.length) { box.hidden = true; return; }
      box.innerHTML = j.items.map(s => `<div data-t="${esc(s.text)}"><span>${esc(s.text)}</span><small>${esc(s.hint)}</small></div>`).join('');
      box.hidden = false;
    } catch { $('#suggest').hidden = true; }
  }, 140);
});
$('#suggest').addEventListener('click', e => {
  const row = e.target.closest('[data-t]');
  if (!row) return;
  $('#q').value = row.dataset.t;
  $('#suggest').hidden = true;
  run();
});

/* ── 检索计划面板 ────────────────────────── */
function renderPlan(plan) {
  const kw = (plan.keywords || []).map(k =>
    `<span class="${k.role === 'primary' ? 'p' : ''}" title="${esc(k.from)}">${esc(k.term)}</span>`).join('');
  const vs = (plan.variants || []).map(v => `
    <div class="variant" data-id="${esc(v.id)}">
      <input type="checkbox" checked>
      <span class="tag">${esc(v.label)}</span>
      <code class="vq" contenteditable="true" spellcheck="false">${esc(v.q)}</code>
      <span class="t">${esc(v.sort || '')}</span>
    </div>`).join('');
  $('#planBox').innerHTML = `
    <div class="panel">
      <h3>检索计划 · 主词 ${esc(plan.primary || '-')}${plan.lang ? ' · ' + esc(plan.lang) : ''}</h3>
      <div class="kw">${kw || '<span>无</span>'}</div>
      ${vs || '<div style="color:var(--dim);font-size:12px">没有生成检索式</div>'}
    </div>`;
  state.customQueries = null;
}

function collectCustom() {
  const rows = $$('#planBox .variant');
  if (!rows.length) return null;
  const keep = [];
  let dirty = false;
  for (const row of rows) {
    const cb = row.querySelector('input[type=checkbox]');
    const code = row.querySelector('.vq');
    const original = (state.plan.variants.find(v => v.id === row.dataset.id) || {}).q;
    if (!cb.checked) { dirty = true; continue; }
    if (code.textContent.trim() !== original) dirty = true;
    keep.push(code.textContent.trim());
  }
  return dirty ? keep : null;
}

$('#planBox').addEventListener('change', () => { state.customQueries = collectCustom(); });
$('#planBox').addEventListener('input', () => { state.customQueries = collectCustom(); });

/* ── 搜索 ────────────────────────────────── */
function buildUrl(q) {
  const p = new URLSearchParams({ q });
  const lang = $('#lang').value; if (lang) p.set('lang', lang);
  p.set('minStars', $('#minStars').value || '0');
  p.set('updated', $('#updated').value || '0');
  p.set('sort', $('#sortMode').value || 'relevance');
  p.set('limit', $('#limit').value || '30');
  if ($('#archived').checked) p.set('archived', '1');
  if ($('#license').checked) p.set('license', '1');
  if (state.customQueries && state.customQueries.length) {
    p.set('extra', state.customQueries.join(';'));
    p.set('maxQueries', String(state.customQueries.length));
  }
  return '/api/stream?' + p.toString();
}

function setStatus(html) { $('#status').innerHTML = html; }
function progressBar(done, of) {
  const pct = of ? Math.round((done / of) * 100) : 0;
  return `<div class="bar"><i style="width:${pct}%"></i></div>`;
}

function run() {
  const q = $('#q').value.trim();
  if (!q) return;
  if (state.es) { state.es.close(); state.es = null; }

  state.q = q;
  state.items = new Map();
  state.buckets = 0; state.of = 0; state.done = false; state.selected = -1; state.warnings = [];
  $('#out').innerHTML = '';
  $('#planBox').innerHTML = '';
  $('#go').disabled = true;
  setStatus(`<span class="spin"></span> 编译检索式…`);
  pushHistory(q);

  const es = new EventSource(buildUrl(q));
  state.es = es;
  const t0 = Date.now();

  es.onmessage = ev => {
    let m;
    try { m = JSON.parse(ev.data); } catch { return; }

    if (m.type === 'plan') {
      state.plan = m.plan;
      state.of = (m.plan.variants || []).length;
      renderPlan(m.plan);
      setStatus(`<span class="spin"></span> ${state.of} 路并发检索中… ${progressBar(0, state.of)}`);
      return;
    }

    if (m.type === 'bucket') {
      state.buckets++;
      for (const it of m.items || []) {
        const prev = state.items.get(it.full_name);
        if (!prev || it.score > prev.score) state.items.set(it.full_name, it);
      }
      setStatus(`<span class="spin"></span> ${m.progress.done}/${m.progress.of} 路已回 · ${state.items.size} 条候选 · 「${esc(m.label)}」${num(m.count)} 条${m.cached ? '（缓存）' : ''} ${progressBar(m.progress.done, m.progress.of)}`);
      renderResults();
      return;
    }

    if (m.type === 'bucketError') {
      state.buckets++;
      state.warnings.push(`「${esc(m.label)}」${esc(m.message)}`);
      setStatus(`${m.progress.done}/${m.progress.of} 路 · 有一路失败 ${progressBar(m.progress.done, m.progress.of)}`);
      return;
    }

    if (m.type === 'done') {
      state.done = true;
      es.close(); state.es = null;
      $('#go').disabled = false;
      if (m.plan) { state.plan = m.plan; renderPlan(m.plan); }
      state.items = new Map((m.results || []).map(r => [r.full_name, r]));
      state.native = m.native || [];
      state.warnings = (m.warnings || []).slice();
      renderResults(true);
      const s = m.stats || {};
      setStatus(`完成 · ${s.candidates ?? state.items.size} 条候选 → 去重 ${s.afterDedupe ?? '-'} → 过滤 ${s.afterFilter ?? '-'} · ${((Date.now() - t0) / 1000).toFixed(1)}s`);
      refreshHealth();
      return;
    }

    if (m.type === 'error') {
      state.done = true;
      es.close(); state.es = null;
      $('#go').disabled = false;
      $('#out').innerHTML = `<div class="err">${esc(m.message)}</div>`;
      setStatus('出错了');
    }
  };

  es.onerror = () => {
    if (state.done) return;
    state.done = true;
    if (state.es) { state.es.close(); state.es = null; }
    $('#go').disabled = false;
    if (!state.items.size) $('#out').innerHTML = `<div class="err">连接中断（服务是否还在 7788？）</div>`;
    else renderResults(true);
  };
}

/* ── 结果渲染 ────────────────────────────── */
function sortItems(list) {
  const mode = $('#sortMode').value;
  const a = [...list];
  const ts = x => new Date(x.pushed_at || 0).getTime();
  const ty = x => x.stars / Math.max((Date.now() - new Date(x.created_at || 0).getTime()) / 3.15e10, 0.4);
  if (mode === 'stars') return a.sort((x, y) => y.stars - x.stars);
  if (mode === 'recent') return a.sort((x, y) => ts(y) - ts(x));
  if (mode === 'trending') return a.sort((x, y) => ty(y) - ty(x));
  return a.sort((x, y) => y.score - x.score);
}

function favSet() {
  try { return new Set(JSON.parse(localStorage.getItem(FKEY) || '[]').map(f => f.full_name)); } catch { return new Set(); }
}

function renderResults(final = false) {
  const limit = Number($('#limit').value) || 30;
  const list = sortItems([...state.items.values()]);
  if (!list.length) {
    if (final) $('#out').innerHTML = '<div class="empty">没搜到。换个说法，或者补一个具体技术词（python / cli / docker / android）。</div>';
    return;
  }
  const favs = favSet();
  const shown = list.filter(r => {
    if ($('#license').checked && !r.license) return false;
    if (!$('#archived').checked && r.archived) return false;
    const u = Number($('#updated').value) || 0;
    if (u && new Date(r.pushed_at || 0).getTime() < Date.now() - u * 864e5) return false;
    return true;
  }).slice(0, limit);

  const warn = state.warnings.length ? `<div class="err">${state.warnings.map(esc).join('<br>')}</div>` : '';
  const cards = shown.map((r, i) => {
    const h = r.health >= 0.7 ? 'ok' : r.health >= 0.4 ? 'mid' : 'no';
    const ht = r.health >= 0.7 ? '健康' : r.health >= 0.4 ? '一般' : '信息少';
    const tps = (r.topics || []).slice(0, 5).map(t => `<span class="topic">${esc(t)}</span>`).join('');
    const why = r.why || {};
    return `<div class="card${state.selected === i ? ' sel' : ''}" data-i="${i}" data-full="${esc(r.full_name)}">
      <div class="top-row">
        <img class="ava" src="${esc(r.avatar || '')}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
        <div style="min-width:0;flex:1">
          <div><a class="repo" href="${esc(r.html_url)}" target="_blank" rel="noopener">${esc(r.owner)}<span class="own">/</span>${esc((r.full_name || '').split('/')[1] || '')}</a>
            ${r.archived ? '<span class="pill no">归档</span>' : ''}</div>
          <div class="desc">${esc(r.description || '(无描述)')}</div>
          <div class="meta">
            <span class="star">★ ${num(r.stars)}</span>
            <span>⑂ ${num(r.forks)}</span>
            <span>${esc(r.lang || '-')}</span>
            <span>${esc(ago(r.pushed_at))}</span>
            ${r.license ? `<span>${esc(r.license)}</span>` : ''}
            <span class="pill ${h}">${ht}</span>
            ${tps}
          </div>
          <div class="hl">命中 <em>${esc((why.matched || []).join(' ')) || '-'}</em>
            · 主词 ${esc(why.primary || '-')} · 评分 ${r.score}
            ${r.sources && r.sources.length > 1 ? ` · ${esc(r.sources.join('+'))}` : ''}
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px">
          <button class="iconbtn fav" title="收藏">${favs.has(r.full_name) ? '★' : '☆'}</button>
          <button class="iconbtn copy" title="复制链接">⧉</button>
        </div>
      </div>
    </div>`;
  }).join('');

  const nativeBlock = (final && state.native && state.native.length) ? `
    <div class="panel" style="margin-top:18px">
      <h3>中文生态 · 按星标</h3>
      ${state.native.map(r => `
        <div class="variant" style="align-items:baseline">
          <a class="mono" style="font-size:12.5px" href="${esc(r.html_url)}" target="_blank" rel="noopener">${esc(r.full_name)}</a>
          <span style="color:var(--warn);font-size:11.5px">★${num(r.stars)}</span>
          <span style="color:var(--dim2);font-size:11.5px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.description || '')}</span>
        </div>`).join('')}
    </div>` : '';

  $('#out').innerHTML = warn + cards + nativeBlock +
    (shown.length < list.length ? `<div class="empty">还有 ${list.length - shown.length} 条被本地过滤/截断</div>` : '');
}

$('#out').addEventListener('click', e => {
  const card = e.target.closest('.card');
  if (!card) return;
  if (e.target.closest('.fav')) {
    const full = card.dataset.full;
    const r = state.items.get(full);
    let favs = [];
    try { favs = JSON.parse(localStorage.getItem(FKEY) || '[]'); } catch { /* noop */ }
    const i = favs.findIndex(f => f.full_name === full);
    if (i >= 0) { favs.splice(i, 1); toast('已取消收藏'); }
    else { favs.unshift({ full_name: full, url: r.html_url, stars: r.stars, desc: r.description, at: Date.now() }); toast('已收藏'); }
    localStorage.setItem(FKEY, JSON.stringify(favs.slice(0, 60)));
    renderResults(); renderFavs();
    return;
  }
  if (e.target.closest('.copy')) {
    const r = state.items.get(card.dataset.full);
    navigator.clipboard?.writeText(r.html_url).then(() => toast('链接已复制')).catch(() => toast('复制失败'));
    return;
  }
  const r = state.items.get(card.dataset.full);
  if (r) window.open(r.html_url, '_blank', 'noopener');
});

/* ── 历史 / 收藏 ─────────────────────────── */
function pushHistory(q) {
  let h = [];
  try { h = JSON.parse(localStorage.getItem(HKEY) || '[]'); } catch { /* noop */ }
  h = h.filter(x => x.q !== q);
  h.unshift({ q, at: Date.now() });
  localStorage.setItem(HKEY, JSON.stringify(h.slice(0, 15)));
  renderHist();
}

function renderHist() {
  let h = [];
  try { h = JSON.parse(localStorage.getItem(HKEY) || '[]'); } catch { /* noop */ }
  $('#hist').innerHTML = h.length ? h.map(x =>
    `<div class="item" data-q="${esc(x.q)}"><span>${esc(x.q)}</span><span class="x" data-del="${esc(x.q)}">×</span></div>`
  ).join('') : '<div style="color:var(--dim2);font-size:12px">还没有</div>';
}

function renderFavs() {
  let f = [];
  try { f = JSON.parse(localStorage.getItem(FKEY) || '[]'); } catch { /* noop */ }
  $('#favs').innerHTML = f.length ? f.map(x =>
    `<div class="item" data-open="${esc(x.url)}"><span>${esc(x.full_name)}</span><span class="x" data-unfav="${esc(x.full_name)}">×</span></div>`
  ).join('') : '<div style="color:var(--dim2);font-size:12px">点卡片上的 ☆ 收藏</div>';
}

$('#hist').addEventListener('click', e => {
  const del = e.target.closest('[data-del]');
  if (del) {
    let h = [];
    try { h = JSON.parse(localStorage.getItem(HKEY) || '[]'); } catch { /* noop */ }
    localStorage.setItem(HKEY, JSON.stringify(h.filter(x => x.q !== del.dataset.del)));
    renderHist(); return;
  }
  const it = e.target.closest('[data-q]');
  if (it) { $('#q').value = it.dataset.q; run(); }
});

$('#favs').addEventListener('click', e => {
  const un = e.target.closest('[data-unfav]');
  if (un) {
    let f = [];
    try { f = JSON.parse(localStorage.getItem(FKEY) || '[]'); } catch { /* noop */ }
    localStorage.setItem(FKEY, JSON.stringify(f.filter(x => x.full_name !== un.dataset.unfav)));
    renderFavs(); renderResults(); return;
  }
  const op = e.target.closest('[data-open]');
  if (op) window.open(op.dataset.open, '_blank', 'noopener');
});

/* ── 交互 ────────────────────────────────── */
$('#go').onclick = run;
$('#q').addEventListener('keydown', e => {
  if (e.key === 'Enter') { $('#suggest').hidden = true; run(); }
  if (e.key === 'Escape') $('#suggest').hidden = true;
});
for (const id of ['sortMode', 'updated', 'license', 'archived', 'limit']) {
  $('#' + id).addEventListener('change', () => { if (state.done || state.items.size) renderResults(true); });
}
$('#lang').addEventListener('change', () => { if (state.q) run(); });

document.addEventListener('keydown', e => {
  if (e.target.matches('input,textarea,[contenteditable="true"]')) {
    if (e.key === 'Escape') e.target.blur();
    return;
  }
  if (e.key === '/') { e.preventDefault(); $('#q').focus(); return; }
  const cards = $$('#out .card');
  if (!cards.length) return;
  if (e.key === 'j' || e.key === 'k') {
    e.preventDefault();
    state.selected = e.key === 'j'
      ? Math.min(state.selected + 1, cards.length - 1)
      : Math.max(state.selected - 1, 0);
    cards.forEach((c, i) => c.classList.toggle('sel', i === state.selected));
    cards[state.selected]?.scrollIntoView({ block: 'nearest' });
  }
  if (e.key === 'Enter' && state.selected >= 0) {
    const r = state.items.get(cards[state.selected].dataset.full);
    if (r) window.open(r.html_url, '_blank', 'noopener');
  }
});

/* ── 设置对话框 ───────────────────────────── */
const dlg = $('#dlg');
$('#btnSettings').onclick = async () => {
  try {
    const j = await (await fetch('/api/config')).json();
    $('#tokenInput').value = '';
    $('#tokenInput').placeholder = j.hasToken ? `已配置 ${j.token}，输入新的覆盖` : 'ghp_…';
    $('#cfgPath').textContent = j.path;
  } catch { /* noop */ }
  dlg.showModal();
};
$('#btnClose').onclick = () => dlg.close();
$('#btnClear').onclick = async () => {
  await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: '' }) });
  toast('token 已清空'); dlg.close(); refreshHealth();
};
$('#btnSave').onclick = async () => {
  const token = $('#tokenInput').value.trim();
  const r = await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) });
  const j = await r.json();
  toast(j.hasToken ? 'token 已保存' : 'token 已清空');
  dlg.close(); refreshHealth();
};

/* ── 启动 ────────────────────────────────── */
renderHist(); renderFavs(); refreshHealth();
fetch('/api/config').then(r => r.json()).then(j => {
  if (j.lang) $('#lang').value = j.lang;
  if (j.sort) $('#sortMode').value = j.sort;
}).catch(() => {});
$('#q').focus();
