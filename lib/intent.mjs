// 意图编译 v3
// 修掉的坑：单字"转/成/个/在/里/用"当连接词会把"转码/个人财务/在线/公里/用户"吃坏。
// 现在连接词只收确定的词组，"转"只在后面跟英文时才抹（网页转markdown）。

import { CONCEPTS, QUALIFIERS, LANGS, STAR_INTENT, FRESH_INTENT, BRANDS } from './lexicon.mjs';

// 只收确定安全的词组
const PAIRS = [
  '转换成', '转化为', '转成', '转为', '变成', '做成', '改成', '弄成', '搞成',
  '用来', '用于', '实现', '帮我', '帮忙', '我想', '我要', '想要', '需要',
  '有没有', '能不能', '可不可以', '一个', '一款', '一些', '一点',
  '找个', '找一下', '推荐', '类似', '可以', '能够', '支持', '最好', '希望',
  '这种', '那种', '以及', '或者', '还有'
].sort((a, b) => b.length - a.length);

// 极安全的单字（只可能是虚词）
const SINGLE = ['把', '的', '了', '吗', '呢', '吧', '呀', '啊', '请'];

const STOP_EN = new Set(['the', 'a', 'an', 'to', 'for', 'of', 'and', 'or', 'with', 'that',
  'this', 'is', 'it', 'can', 'be', 'my', 'me', 'i', 'you', 'want', 'need', 'find', 'some',
  'github', 'repo', 'project', 'tool', 'app', 'open', 'source']);

export function norm(s) {
  let t = String(s || '').toLowerCase();
  for (const p of PAIRS) t = t.split(p).join('');
  for (const c of SINGLE) t = t.split(c).join('');
  t = t.replace(/转(?=[a-z0-9])/g, '');         // 网页转markdown -> 网页markdown；转码 保留
  return t.replace(/[^a-z0-9+#.\u4e00-\u9fa5]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function parts(trigger) {
  const n = norm(trigger);
  return {
    runs: n.match(/[\u4e00-\u9fa5]{2,}/g) || [],
    // 允许数字开头（3d / 2fa），但整体至少 2 字符，避免 3d 被拆成 "d"
    ascii: (n.match(/[a-z0-9][a-z0-9+#.]{1,}/g) || []).filter(t => !/^[0-9]+$/.test(t))
  };
}

// 短词要按边界匹配：ntext 已去掉空白，边界只会是中文或数字
function asciiHit(ntext, a) {
  const re = new RegExp(`(^|[^a-z0-9])${a.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z0-9]|$)`);
  return re.test(ntext);
}

function matchLen(concept, ntext, hasAscii) {
  // 返回命中的最长触发词长度，0 表示没命中。
  // 用长度而不是布尔，是为了让「系统提示词泄露」优先于「提示词」这种泛词。
  let best = 0;
  for (const zh of concept.zh) {
    const { runs, ascii } = parts(zh);
    if (!runs.length && !ascii.length) continue;

    if (!runs.length) {
      if (ascii.some(a => asciiHit(ntext, a))) best = Math.max(best, zh.length);
      continue;
    }
    if (!runs.every(r => ntext.includes(r))) continue;
    if (ascii.length) {
      // 触发词里带英文就必须真出现：「插件」不能命中「ida插件」
      if (ascii.some(a => asciiHit(ntext, a))) best = Math.max(best, zh.length);
      continue;
    }
    best = Math.max(best, zh.length);
  }
  return best;
}

export function compile(raw, opts = {}) {
  const original = String(raw || '').toLowerCase();
  const excluded = [];
  const positive = original.replace(/(?:不要|不用|不需要|排除|不支持|without\s+|exclude\s+|not\s+)(?:\s*)(docker|python|java(?:script)?|typescript|rust|go|容器|安卓|android|教程|tutorial)\b/gi,
    (_, word) => { excluded.push(({ '容器': 'docker', '安卓': 'android', '教程': 'tutorial' })[word] || word); return ' '; });
  const ntext = norm(positive);
  const required = /双链|双向链接|\bbacklinks?\b/i.test(positive) ? ['backlinks'] : [];
  const hasAscii = /[a-z]{2,}/.test(ntext);
  const maxQueries = Math.min(Math.max(Number(opts.maxQueries) || 4, 1), 5);

  const keywords = [];
  const push = (term, weight, src, role) => {
    const t = String(term || '').trim().toLowerCase();
    if (!t) return;
    const found = keywords.find(k => k.term === t);
    if (found) { found.weight = Math.max(found.weight, weight); return; }
    keywords.push({ term: t, weight, src, role });
  };

  // 语言
  let lang = null;
  for (const item of LANGS) {
    if (item.zh.some(zh => /[a-z]/i.test(zh) ? asciiHit(ntext, norm(zh)) : ntext.includes(norm(zh)))) { lang = item.en; break; }
  }
  lang = opts.lang || lang;

  // 修饰意图
  const qualKws = [];
  const topics = [];
  for (const q of QUALIFIERS) {
    if (q.zh.some(zh => /[a-z]/i.test(zh) ? asciiHit(ntext, norm(zh)) : ntext.includes(norm(zh)))) {
      for (const kw of q.kw) qualKws.push(kw);
      for (const t of q.topic) if (!topics.includes(t)) topics.push(t);
    }
  }

  // 概念：长触发词优先
  const ordered = [...CONCEPTS].sort((a, b) =>
    Math.max(...b.zh.map(z => z.length)) - Math.max(...a.zh.map(z => z.length)));
  const hits = ordered
    .map(c => ({ c, len: matchLen(c, ntext, hasAscii) }))
    .filter(h => h.len > 0)
    .sort((a, b) => b.len - a.len)
    .map(h => h.c);

  const hitZh = [];
  let primarySet = false;
  for (const c of hits) {
    for (const t of c.topic) if (!topics.includes(t)) topics.push(t);
    for (const [i, en] of c.en.entries()) {
      const role = (i === 0 && !primarySet) ? 'primary' : 'secondary';
      if (role === 'primary') primarySet = true;
      push(en, i === 0 ? 1 : 0.85 - i * 0.05, 'concept', role);
    }
    for (const zh of c.zh) {
      const nz = norm(zh);
      if (!/[\u4e00-\u9fa5]{2,}/.test(nz)) continue;
      const runs = nz.match(/[\u4e00-\u9fa5]{2,}/g) || [];
      if (!runs.every(r => ntext.includes(r))) continue;
      const rawZh = zh.replace(/\s+/g, '');
      if (rawZh.length >= 2 && !hitZh.includes(rawZh)) hitZh.push(rawZh);
      break;
    }
  }
  hitZh.sort((a, b) => b.length - a.length);
  hitZh.length = Math.min(hitZh.length, 3);

  // 只认识一部分词时，其余中文仍是需求，不能因为出现 python/dsh 就丢掉。
  let unmappedText = ntext;
  const knownChinese = [...hitZh, ...QUALIFIERS.flatMap(q => q.zh), ...LANGS.flatMap(l => l.zh),
    ...STAR_INTENT.flatMap(s => s.zh), ...FRESH_INTENT.flatMap(f => f.zh), ...(required.length ? ['双链', '双向链接'] : []),
    '软件', '工具', '项目', '功能', '关于', '搜索', '寻找', '找一个'];
  for (const phrase of knownChinese.sort((a, b) => b.length - a.length)) {
    for (const run of norm(phrase).match(/[\u4e00-\u9fa5]{2,}/g) || []) unmappedText = unmappedText.split(run).join(' ');
  }
  const unmappedTerms = [...new Set(unmappedText.match(/[\u4e00-\u9fa5]{2,}/g) || [])];

  // 品牌 / 生态
  const brands = [];
  for (const b of BRANDS) {
    if (b.zh.some(zh => /[a-z]/i.test(zh) ? asciiHit(ntext, norm(zh)) : ntext.includes(norm(zh)))) {
      for (const en of b.en) if (!brands.includes(en)) brands.push(en);
    }
  }

  // 用户自写英文
  for (const tok of positive.match(/[a-z][a-z0-9+#.-]*/g) || []) {
    if (tok.length < 2 || STOP_EN.has(tok)) continue;
    push(tok.replace(/[.]+$/, ''), 0.9, 'user', primarySet ? 'secondary' : 'primary');
    if (!primarySet) primarySet = true;
  }

  // 热度 / 新鲜
  let stars = null, fresh = false;
  for (const s of STAR_INTENT) if (s.zh.some(z => original.includes(z))) { stars = s.stars; break; }
  for (const f of FRESH_INTENT) if (f.zh.some(z => original.includes(z))) { fresh = true; break; }

  for (const kw of required) push(kw, 1.1, 'requirement', 'secondary');
  if (primarySet) for (const kw of qualKws) push(kw, 0.8, 'qualifier', 'secondary');
  keywords.sort((a, b) => (a.role !== b.role ? (a.role === 'primary' ? -1 : 1) : b.weight - a.weight));
  if (keywords.length > 10) keywords.length = 10;

  const terms = keywords.map(k => k.term);
  const primary = terms[0] || '';
  const freshQ = fresh ? `pushed:>${new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10)}` : '';
  const langQ = lang ? `language:${lang}` : '';
  const starQ = stars ? `stars:${stars}` : '';

  const variants = [];
  const mk = (kind, label, q, sort) => {
    const s = [q, ...excluded.map(t => `NOT ${t}`)].join(' ').replace(/\s+/g, ' ').trim();
    if (!s || variants.some(x => x.q === s)) return;
    variants.push({ id: `v${variants.length + 1}`, kind, label, q: s, sort: sort || '' });
  };

  const rawZh = String(raw || '').trim();
  const custom = Array.isArray(opts.queries) && opts.queries.length
    ? opts.queries.map((q, i) => ({ id: `c${i + 1}`, kind: 'custom', label: '自定义', q: String(q), sort: '' }))
    : null;
  if ((!primary || (!hits.length && unmappedTerms.length)) && rawZh) {
    // 词典没覆盖的话，别认输：把原话直接丢给 GitHub（它也索引中文描述和 readme）
    const nativeTerms = unmappedTerms.length ? unmappedTerms : [rawZh];
    const languageTerms = new Set(LANGS.flatMap(l => l.zh.map(norm)));
    const anchors = brands.length ? [brands[0]] : keywords.filter(k => k.src === 'user' && !languageTerms.has(k.term)).map(k => k.term);
    const scope = ['in:name,description,readme', langQ, starQ, freshQ].filter(Boolean).join(' ');
    mk('native', '原话直搜', [...anchors, ...nativeTerms, scope].join(' '));
    mk('broad-raw', '原话宽搜', [...(brands.length ? [brands[0]] : []), ...nativeTerms, scope].join(' '), 'stars');
    return {
      raw: rawZh, keywords: nativeTerms.map((term, i) => ({term, weight: 1, src: 'original', role: i ? 'secondary' : 'primary'})),
      primary: nativeTerms[0], zhTerms: nativeTerms, brands,
      lang, stars, topics, unmappedTerms,
      variants: (custom || variants).slice(0, maxQueries), hasAscii, excluded, required, fallback: true
    };
  }

  if (primary) {
    const second = terms[1] || '';
    const third = terms[2] || '';
    if (unmappedTerms.length) {
      const anchor = brands[0] || keywords.find(k => k.src === 'user' && !LANGS.some(l => l.zh.some(z => norm(z) === k.term)))?.term;
      mk('native-detail', '保留原词', [anchor, hitZh[0] || primary, ...unmappedTerms, 'in:name,description,readme', langQ, starQ, freshQ, 'archived:false'].filter(Boolean).join(' '));
    }
    // 明确指定生态时，先检索「生态 + 用途」，避免宽泛高星项目挤占查询预算。
    // 名称和简介优先，README 补召回；避免大型插件清单挤掉小型专用项目。
    if (brands.length) {
      const scope = ['in:name,description', langQ, starQ, freshQ, 'archived:false'].filter(Boolean).join(' ');
      mk('brand', '生态', `${brands[0]} ${primary} ${scope}`);
      if (hitZh.length) mk('brand-native', '生态中文', `${brands[0]} ${hitZh[0]} ${scope}`);
      if (brands[1]) mk('brand-alias', '生态别名', `${brands[1]} ${primary} ${scope.replace('in:name,description', 'in:name,description,readme')}`);
    }
    mk('exact', '精确', [primary, second, 'in:name,description', langQ, starQ, freshQ, 'archived:false'].filter(Boolean).join(' '));
    // 宽泛只留主词：topic 全 AND 起来会把结果卡成 0，标签放到打分里做信号
    mk('broad', '宽泛', [primary, 'in:name,description', langQ, starQ, freshQ].filter(Boolean).join(' '), 'stars');
    if (hitZh.length) mk('native', '中文原话', [hitZh[0], 'in:name,description,readme', langQ, starQ, freshQ].filter(Boolean).join(' '));
    if (second) mk('combo', '组合', [second, third, primary, starQ].filter(Boolean).join(' '), 'stars');
  }

  // 自定义：调用方传 queries 数组就直接用

  return {
    raw: String(raw || ''),
    keywords,
    primary,
    zhTerms: hitZh,
    brands,
    lang: opts.lang || lang,
    stars,
    topics,
    excluded,
    required,
    unmappedTerms,
    variants: (custom || variants).slice(0, maxQueries)
  };
}

/** 给 UI 做输入联想 */
export function suggest(text, limit = 10) {
  const q = String(text || '').trim().toLowerCase();
  if (!q) return [];
  const out = [];
  for (const c of CONCEPTS) {
    for (const zh of c.zh) {
      if (zh.includes(q) || (q.length >= 2 && zh.slice(0, 2) === q.slice(0, 2))) {
        out.push({ text: zh, hint: c.en.slice(0, 2).join(' / ') });
        break;
      }
    }
    if (out.length >= limit * 2) break;
  }
  const seen = new Set();
  return out.filter(o => (seen.has(o.text) ? false : (seen.add(o.text), true))).slice(0, limit);
}

