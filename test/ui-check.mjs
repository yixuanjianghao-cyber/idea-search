// 静态一致性检查：app.js 用到的 DOM id 必须在 index.html 存在
import { readFileSync } from 'node:fs';
const html = readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
const js = readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
const ids = new Set([...html.matchAll(/id="([^"]+)"/g)].map(m => m[1]));
const used = [...new Set([...js.matchAll(/\$\('#([A-Za-z0-9_-]+)'\)/g)].map(m => m[1]))];
const missing = used.filter(u => !ids.has(u));
console.log('html id:', [...ids].join(', '));
console.log('js 用到:', used.join(', '));
if (missing.length) { console.log('缺失:', missing.join(', ')); process.exit(1); }
const css = readFileSync(new URL('../public/style.css', import.meta.url), 'utf8');
for (const cls of ['card', 'panel', 'variant', 'suggest', 'toast', 'badge']) {
  if (!css.includes('.' + cls)) { console.log('CSS 缺样式类:', cls); process.exit(1); }
}
console.log('OK · DOM 与样式对齐');
