// 仓库解读：把 README / 目录 / 清单文件翻成大白话
// 只调 4 次 API：repo、readme、contents、manifest（可选）。缓存 30 分钟。

import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, renameSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { token as readToken, configPath } from '../config.mjs';
import { apiGet, tokenPresent } from './github.mjs';
import { usageSteps, deployScript } from './deployment.mjs';
import { selectWindowsAsset, launchPlan } from './launch.mjs';
import { publicRepo } from './public-repo.mjs';
export { usageSteps } from './deployment.mjs';

const TTL = 30 * 60 * 1000;
const cache = new Map();
const CACHE_FILE = join(dirname(configPath), '.github-finder-analysis-cache.json');
function readDiskCache() {
  try { return JSON.parse(readFileSync(CACHE_FILE,'utf8')); } catch { return {}; }
}
function writeDiskCache(key,data) {
  try {
    const records=readDiskCache(); records[key]={at:Date.now(),data};
    const entries=Object.entries(records).filter(([,r])=>Date.now()-r.at<86400000).sort((a,b)=>b[1].at-a[1].at).slice(0,80);
    mkdirSync(dirname(CACHE_FILE),{recursive:true});
    writeFileSync(CACHE_FILE+'.tmp',JSON.stringify(Object.fromEntries(entries)),{mode:0o600}); renameSync(CACHE_FILE+'.tmp',CACHE_FILE);
  } catch { /* Analysis remains usable if caching is unavailable. */ }
}

const STACK = [
  { file: 'package.json', stack: 'Node / JavaScript', how: 'node' },
  { file: 'tsconfig.json', stack: 'TypeScript', how: 'node' },
  { file: 'requirements.txt', stack: 'Python', how: 'python' },
  { file: 'pyproject.toml', stack: 'Python', how: 'python' },
  { file: 'setup.py', stack: 'Python', how: 'python' },
  { file: 'go.mod', stack: 'Go', how: 'go' },
  { file: 'Cargo.toml', stack: 'Rust', how: 'rust' },
  { file: 'pom.xml', stack: 'Java / Maven', how: 'java' },
  { file: 'build.gradle', stack: 'Java / Gradle', how: 'java' },
  { file: 'Gemfile', stack: 'Ruby', how: 'ruby' },
  { file: 'composer.json', stack: 'PHP', how: 'php' },
  { file: 'docker-compose.yml', stack: 'Docker Compose', how: 'compose' },
  { file: 'docker-compose.yaml', stack: 'Docker Compose', how: 'compose' },
  { file: 'compose.yml', stack: 'Docker Compose', how: 'compose' },
  { file: 'compose.yaml', stack: 'Docker Compose', how: 'compose' },
  { file: 'Dockerfile', stack: 'Docker', how: 'docker' },
  { file: 'Makefile', stack: 'Make', how: 'make' },
  { file: 'Cargo.lock', stack: 'Rust', how: 'rust' },
];

const KEY_HINT = /(api[_-]?key|access[_-]?token|openai|anthropic|secret|\.env)/i;

export function relevantReadme(md) {
  let skippedLevel = 0;
  return String(md || '').split('\n').filter(line => {
    const heading = line.match(/^\s*(#{1,6})\s+(.+)/);
    if (heading && skippedLevel && heading[1].length <= skippedLevel) skippedLevel = 0;
    if (heading && /sponsors?|advertis|contribut|acknowledg|donat|赞助|广告|致谢|交流与支持/i.test(heading[2])) skippedLevel = heading[1].length;
    return !skippedLevel;
  }).join('\n');
}

function stripMd(s) {
  return String(s || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[[^\]]*]\([^)]*\)/g, ' ')
    .replace(/\[!\[[^\]]*]\([^)]*\)]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)]\([^)]*\)/g, '$1')     // [文字](链接) -> 文字
    .replace(/<[^>]+>/g, ' ')
    .replace(/^\s*[#>|\-*]+\s*/gm, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function firstParagraph(md) {
  const blocks = String(md || '').split(/\n\s*\n/);
  const cands = [];
  for (const b of blocks) {
    const t = stripMd(b);
    if (t.length < 40 || t.length > 400) continue;
    if (/^\.\.\s/.test(b.trim())) continue;                     // rst 指令
    if (/contents::|toctree|:depth:|backlinks|:alt:/i.test(b)) continue;
    if (/(badge|build status|workflow status|codecov|pypi|npm version|license: |stars: |forks: )/i.test(b)) continue;
    if ((t.match(/https?:/g) || []).length > 1) continue;         // 纯链接行
    if (/^(installation|usage|install|getting started|table of contents|目录|安装)\b/i.test(t)) continue;
    // 表格 / 语言列表 / 徽章行：竖线多的基本都不是人话
    if ((b.match(/\|/g) || []).length >= 2) continue;
    if ((t.match(/\b(script|translation|arabic|korean|japanese)\b/gi) || []).length >= 3) continue;
    if (/sponsor|advertisement|promo|affiliate|follow us|join our (discord|telegram)|star history/i.test(t)) continue;
    if (/^[\p{Emoji_Presentation}\u2600-\u27bf\u2b00-\u2bff]/u.test(t)) continue;
    if (/^[\w#().'/ -]+(\s*\|\s*[\w#().'/ -]+){2,}$/.test(t)) continue;
    cands.push(t);
  }
  // 中文说明优先，其次第一段像人话的
  const zh = cands.find(t => /[\u4e00-\u9fa5]{6,}/.test(t));
  return (zh || cands[0] || '').slice(0, 280);
}

function detectStack(files, manifest, topics = []) {
  const names = files.map(f => f.toLowerCase());
  const found = [];
  for (const s of STACK) if (names.includes(s.file.toLowerCase())) found.push(s);

  const has = n => names.includes(n);
  const isAndroid = /android/i.test([].concat(topics).join(' '))
    || has('androidmanifest.xml')
    || (has('gradlew') && names.some(n => /setting\.gradle|build\.gradle/.test(n)));

  const stack = [...new Set(found.map(f => f.stack))];
  if (isAndroid) stack.unshift('Android');

  // 优先级：容器 > 移动端 > 语言运行时 > 源码
  let how = 'clone';
  const pick = h => found.find(f => f.how === h);
  if (pick('compose')) how = 'compose';
  else if (isAndroid) how = 'android';
  else if (pick('docker')) how = 'docker';
  else if (pick('node')) how = 'node-start';
  else if (pick('python')) how = 'python';
  else if (pick('go')) how = 'go';
  else if (pick('rust')) how = 'rust';
  else if (pick('java')) how = 'java';
  else if (pick('ruby')) how = 'ruby';
  else if (pick('php')) how = 'php';
  else if (pick('make')) how = 'make';

  if (manifest?.scripts) {
    if (manifest.scripts.dev && !manifest.scripts.start && how !== 'compose' && how !== 'docker' && !isAndroid) how = 'node-dev';
    else if (manifest.scripts.start && how !== 'compose' && !isAndroid) how = 'node-start';
  }
  return { stack, how, found };
}

// ── 判断这是个什么东西：这一步决定「怎么用」讲不讲得明白 ──────────
export function detectKind(repo, files, manifest, readme) {
  const name = repo.name.toLowerCase();
  const desc = (repo.description || '').toLowerCase();
  const blob = (desc + " " + readme.slice(0, 8000)).toLowerCase();
  const has = f => files.some(x => x.toLowerCase() === f);

  const runnableRoot = files.some(f => /^(?:package\.json|pyproject\.toml|setup\.py|requirements\.txt|dockerfile|(?:docker-)?compose\.ya?ml|go\.mod|cargo\.toml|pom\.xml)$/i.test(f));
  if (!runnableRoot && /api/i.test(desc) && /(?:免费|转发|中转).{0,20}api|api.{0,20}(?:免费|转发|中转)/i.test(desc)
      && /api.?key/i.test(readme) && /转发Host|该API Key用于转发API|注册并绑定Github免费使用/i.test(readme)) {
    return {kind:'api-service',hint:'这是在线 API 服务的接入说明和示例；当前根目录没有可独立部署的服务入口，需要申请该服务的 Key 后接入客户端'};
  }

  // 数据集先判：名字里带 prompts 的数据集不该被当成提示词合集
  if (/dataset|corpus|benchmark data|数据集|语料/.test(desc) || (files.some(f => f.toLowerCase() === 'data') && /dataset|样本/.test(blob))) {
    return { kind: 'dataset', hint: '这是数据集：下载下来喂给程序用，不是能双击打开的软件' };
  }
  // 提示词合集：名字/描述里就是 prompts，且不是数据集、不是包
  if (/prompt|jailbreak|提示词|破甲/.test(name + " " + desc) && /prompt|提示词|破甲/.test(blob) && !manifest) {
    return { kind: 'prompts', hint: '这是提示词/文本合集：不用装，复制内容就能用' };
  }
  if (/\bawesome\b|curated list|资源列表|项目列表|工具列表/.test(desc + " " + name)) {
    return { kind: 'awesome', hint: '这是一份清单/合集，不是软件：没有东西可装，翻目录找你要的项目就行' };
  }
  if (/\bcookbooks?\b|code examples|example collection|示例合集|代码示例|示例与教程/.test(name + ' ' + desc)
      && /examples?|guides?|tutorials?|notebooks?|示例|教程/i.test(desc + ' ' + readme.slice(0, 2500))) {
    return { kind: 'examples', hint: '这是代码示例与教程集合：按案例学习和运行，各案例可能有独立依赖与配置' };
  }
  if (has('docker-compose.yml') || has('docker-compose.yaml') || has('compose.yml') || has('compose.yaml')) {
    return { kind: 'app', hint: '这是能直接跑起来的服务：用 Docker 起，起来之后是网页或 API' };
  }
  if (/\bdesktop (?:app|application|client)\b|桌面(?:应用|软件|客户端)/i.test(desc + ' ' + readme.slice(0, 1000)) || has('src-tauri')) {
    return {kind:'desktop',hint:'这是桌面软件；优先使用作者发布的安装包，源码构建方式另行核对'};
  }
  if (manifest?.type === 'npm' && manifest.scripts && (manifest.scripts.start || manifest.scripts.dev)) {
    return { kind: 'app', hint: '这是一个应用：装依赖、启动脚本一跑就有东西看' };
  }
  if (manifest?.type === 'npm' && manifest.bin) {
    return { kind: 'cli', hint: '这是命令行工具：装完在终端敲它的名字用' };
  }
  if (has('setup.py') || has('pyproject.toml')) {
    const isCli = /console_scripts|entry_points|\[project\.scripts\]/.test(readme);
    return isCli
      ? { kind: 'cli', hint: '这是命令行工具：装完在终端敲它的名字用' }
      : { kind: 'library', hint: '这是给开发者用的库：不是能双击打开的软件，要在你自己的代码里 import 它' };
  }
  if (manifest?.type === 'npm') {
    return { kind: 'library', hint: '这是前端/Node 的库：在你的项目里装它、引用它，不是独立软件' };
  }
  if (/extension|plugin|插件/.test(desc + " " + (repo.topics || []).join(' '))) {
    return { kind: 'plugin', hint: '这是插件：装到你已有的软件里（浏览器 / 编辑器），不能单独打开' };
  }
  return { kind: 'unknown', hint: '看不出类型，大概率是代码或文档仓库，先读 README 前几段' };
}

export function readmeHeadings(md) {
  const out = [];
  for (const line of String(md || '').split('\n')) {
    const m = line.match(/^#{2,3}\s+(.{2,40})$/);
    if (m) {
      const t = m[1].replace(/[*`_]/g, '').trim();
      if (t && !/^(license|contributing|acknowledg|star history)/i.test(t)) out.push(t);
    }
    if (out.length >= 8) break;
  }
  return out;
}

export function readmeCommands(md) {
  const cmds = [];
  for (const block of String(md || '').matchAll(/```[a-z]*\n([\s\S]{0,600}?)```/g)) {
    for (const line of block[1].split('\n')) {
      const t = line.trim().replace(/^\$\s*/, '');
      if (/^(pip3? install|npm (i|install)|yarn|pnpm|go (get|install)|cargo (install|build)|docker (run|compose)|brew install|apt(-get)? install|git clone)/.test(t)) {
        if (!cmds.includes(t) && t.length < 120) cmds.push(t);
      }
    }
    if (cmds.length >= 4) break;
  }
  return cmds;
}

export function needsOf(blob) {
  const out = [];
  if (/\b(cuda|nvidia|gpu|vram)\b/i.test(blob)) out.push('最好有显卡（README 提到 CUDA/GPU）');
  if (/openai_api_key|anthropic_api_key|api[_ -]?key|access[_-]?token/i.test(blob)) out.push('要自己申请 API key');
  if (/\b(postgres|mysql|mongo(db)?|redis)\b/i.test(blob)) out.push('要配数据库');
  if (/\b(docker)\b/i.test(blob)) out.push('推荐用 Docker 跑');
  if (/微信|telegram|discord/.test(blob) && /bot/i.test(blob)) out.push('要注册机器人账号');
  return out.slice(0, 4);
}

function fitFor(repo, query, ctx) {
  const reasons = [];
  let level = 'maybe';

  const q = String(query || '').toLowerCase();
  const hay = `${repo.full_name} ${repo.description || ''} ${(repo.topics || []).join(' ')}`.toLowerCase();
  const words = (q.match(/[a-z][a-z0-9-]{2,}/g) || []).filter(w => !['the', 'for', 'and'].includes(w));
  const hits = words.filter(w => hay.includes(w));

  if (repo.archived) { level = 'poor'; reasons.push('仓库已归档，作者不再维护，遇到问题没人修'); }
  if (ctx.monthsOld > 24 && level !== 'poor') { level = 'maybe'; reasons.push(`已经 ${Math.round(ctx.monthsOld / 12)} 年没更新`); }
  if (!repo.license) { reasons.push('没有许可证，商用前先问作者'); }
  if (ctx.needsKey) { if (level === 'good') level = 'maybe'; reasons.push('要自己申请 API key（README 里提到了），不是装上就能用'); }
  const runtime = {
    compose: '需要 Docker Desktop；还需核对配置与端口',
    docker: '需要 Docker；启动参数尚需核对',
    android: '手机 App，下 APK 装上就行，不用部署',
    python: '本地跑，要先装 Python',
    'node-dev': '本地跑，要先装 Node.js',
    'node-start': '本地跑，要先装 Node.js',
    go: '本地跑，要先装 Go',
    rust: '本地跑，要先装 Rust',
    java: '本地跑，要先装 JDK',
    make: '要自己编，有点基础才顺',
    clone: '作者没写构建方式，得自己看 README 摸',
  }[ctx.how];
  if (runtime) reasons.push(runtime);
  if (ctx.how === 'clone') { if (level === 'good') level = 'maybe'; }
  if (repo.stars >= 1000) reasons.push(`${repo.stars} 星；热度不代表兼容性已验证`);
  if (repo.stars < 20) { if (level === 'good') level = 'maybe'; reasons.push('星标较少；成熟度需要进一步检查'); }
  if (hits.length) reasons.unshift(`和你要的「${hits.slice(0, 3).join('、')}」对得上`);

  return { level, reasons: reasons.slice(0, 5) };
}

function risks(repo, ctx) {
  const out = [];
  if (repo.archived) out.push('已归档：只读，不会再有更新');
  if (!repo.license) out.push('无许可证：法律上默认保留所有权利，商用需授权');
  if (ctx.monthsOld > 12) out.push(`最近一次提交在 ${Math.round(ctx.monthsOld)} 个月前`);
  if (ctx.needsKey) out.push('需要第三方 API key / 账号');
  if (repo.issues > repo.stars * 0.3 && repo.stars > 100) out.push('未关闭 issue 很多，维护可能跟不上');
  if (repo.size > 500000) out.push('仓库体积大，clone 慢');
  return out;
}

export async function analyzeRepo(full, query = '', onStage = () => {}) {
  if (!/^[\w.-]+\/[\w.-]+$/.test(full)) throw new Error('仓库名称无效');
  const key = `launch-v2-public|${createHash('sha256').update(readToken()).digest('hex')}|${full}|${query}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL) return { ...hit.data, cached: true };
  const stored=readDiskCache()[key];
  if (stored && Date.now()-stored.at<TTL) return {...stored.data,cached:true,diskCached:true};

  let publicReader = null;
  async function get(path) {
    if (publicReader) return publicReader.get(path);
    try { return await apiGet(path, {noWait:true}); }
    catch (error) {
      if (error.code !== 'RATE_LIMIT') throw error;
      onStage('API 配额已用完，改读公开仓库文件');
      publicReader = await publicRepo(full);
      return publicReader.get(path);
    }
  }
  onStage('读取仓库信息');
  let repo;
  try { repo=await get(`/repos/${full}`); }
  catch(error) {
    if (stored && Date.now()-stored.at<86400000) return {...stored.data,cached:true,diskCached:true,stale:true,quotaNote:'连接失败，显示之前读取的快照。'+error.message};
    throw error;
  }
  const out = {
    full_name: repo.full_name,
    html_url: repo.html_url,
    description: repo.description || '',
    stars: repo.stargazers_count,
    forks: repo.forks_count,
    issues: repo.open_issues_count,
    lang: repo.language,
    license: repo.license?.spdx_id && repo.license.spdx_id !== 'NOASSERTION' ? repo.license.spdx_id : null,
    archived: repo.archived,
    topics: repo.topics || [],
    pushed_at: repo.pushed_at,
    created_at: repo.created_at,
    size: repo.size,
    default_branch: repo.default_branch,
    homepage: repo.homepage || ''
  };

  // README
  onStage('读取 README');
  let readme = '';
  try {
    const r = await get(`/repos/${full}/readme`);
    if (r?.content) readme = Buffer.from(r.content, 'base64').toString('utf8');
  } catch { /* 没 readme 也能分析 */ }

  // 顶层目录：把文件夹和文件分开，藏掉点开头的配置垃圾，人才看得懂
  onStage('扫描目录结构');
  let entries = [];
  try {
    const c = await get(`/repos/${full}/contents/`);
    if (Array.isArray(c)) entries = c;
  } catch { /* 空仓库或权限 */ }
  const dirs = entries.filter(e => e.type === 'dir' && !e.name.startsWith('.')).map(e => e.name);
  const plainFiles = entries.filter(e => e.type === 'file' && !e.name.startsWith('.')).map(e => e.name);
  const files = entries.map(e => e.name);

  // 清单文件（只取一个，省配额）
  let manifest = null;
  onStage('读取依赖清单');
  if (files.includes('package.json')) {
    try {
      const f = await get(`/repos/${full}/contents/package.json`);
      const txt = Buffer.from(f.content || '', 'base64').toString('utf8');
      const j = JSON.parse(txt);
      manifest = { type: 'npm', name: j.name, scripts: j.scripts || {}, bin: j.bin, engines: j.engines || {}, packageManager: j.packageManager || '', deps: Object.keys(j.dependencies || {}).slice(0, 8) };
    } catch { /* ignore */ }
  } else if (files.includes('requirements.txt')) {
    try {
      const f = await get(`/repos/${full}/contents/requirements.txt`);
      const txt = Buffer.from(f.content || '', 'base64').toString('utf8');
      manifest = { type: 'pip', deps: txt.split('\n').map(s => s.trim()).filter(s => s && !s.startsWith('#')).slice(0, 8) };
    } catch { /* ignore */ }
  }

  readme = relevantReadme(readme);
  const readmeExcerpt = String(readme || '')
    .replace(/!\[[^\]]*]\([^)]*\)/g, '')
    .replace(/^\s*\[!\[.*$/gm, '')
    .replace(/<[^>]+>/g, '')
    .slice(0, 6000);

  const { stack, how } = detectStack(files, manifest, repo.topics || []);
  const kind = detectKind({ ...out, name: repo.name, topics: repo.topics || [] }, files, manifest, readme);
  const headings = readmeHeadings(readme);
  const installCmds = readmeCommands(readme);
  const needs = needsOf(readme.slice(0, 12000) + ' ' + (repo.description || ''));
  const runtimeNeed = how === 'python' ? '需要 Python（版本按项目清单）' : how.startsWith('node') ? '需要 Node.js（版本按项目清单）' : ['compose', 'docker'].includes(how) ? '需要 Docker 服务运行' : '';
  if (runtimeNeed && !needs.includes(runtimeNeed)) needs.unshift(runtimeNeed);
  const monthsOld = Math.max(0, (Date.now() - new Date(repo.pushed_at).getTime()) / (1000 * 60 * 60 * 24 * 30));
  const needsKey = KEY_HINT.test(readme.slice(0, 8000)) || (repo.topics || []).includes('openai');
  const ctx = { stack, how, monthsOld, needsKey };

  const what = firstParagraph(readme) || repo.description || '作者没写说明，得看代码。';
  let { steps, commands: autoCmds } = usageSteps(how, {
    ...out, name: repo.name, html_url: repo.html_url
  }, manifest, files);
  if (kind.kind === 'examples') steps = ['打开仓库目录，选择与你需求接近的案例或 Notebook。', '阅读该案例自己的依赖、模型账号与 API key 要求。', '按案例文档运行和修改；尚未核验统一启动入口。'];
  if (kind.kind === 'api-service') steps = ['打开 README 中的注册与 Key 申请说明。', '在支持该接口的客户端中填写服务方提供的 API 地址和 Key。', '按服务文档选择模型并测试连接；申请 Key 不等于在本机部署该服务。'];

  // 作者自己在 README 里写的安装命令最靠谱，放前面
  const commands = [...autoCmds];
  if (kind.kind === 'library' && how === 'python' && /^[\w.-]+$/.test(repo.name) && /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/.test(repo.html_url)) {
    commands.length = 0;
    commands.push(`git clone ${repo.html_url}.git`, `cd ${repo.name}`, 'python -m venv .venv');
    if (files.includes('requirements.txt')) commands.push('.venv\\Scripts\\python.exe -m pip install -r requirements.txt');
    commands.push('.venv\\Scripts\\python.exe -m pip install .');
    steps = ['自动下载源码并建立独立 Python 环境。','安装完成后，按照 README 的接口示例在代码中调用。'];
  }
  if (kind.kind === 'library' && how.startsWith('node') && manifest?.type === 'npm'
      && (!manifest.packageManager || manifest.packageManager.startsWith('npm@'))
      && !files.some(f=>['pnpm-lock.yaml','yarn.lock','bun.lock','bun.lockb'].includes(f))) {
    commands.length = 0;
    commands.push(`git clone ${repo.html_url}.git`, `cd ${repo.name}`, files.includes('package-lock.json') ? 'npm ci' : 'npm install');
    if (manifest.scripts?.build) commands.push('npm run build');
    steps = ['自动下载源码并安装这个库的开发依赖。','按照 README 的导入与接口示例在自己的项目中使用。'];
  }
  if (['examples', 'prompts', 'awesome', 'dataset', 'plugin', 'api-service'].includes(kind.kind)) commands.length = 0;
  let releaseAsset = null;
  if (kind.kind === 'desktop' || kind.kind === 'cli') {
    onStage('查找 Windows 安装包');
    try {
      const release = await get(`/repos/${full}/releases/latest`);
      if (!release.draft && !release.prerelease) releaseAsset = selectWindowsAsset(release.assets, out.full_name);
    } catch { /* Missing release does not invalidate source analysis. */ }
  }

  const brief = {
    ...out,
    what,
    readme: readmeExcerpt,
    kind: kind.kind,
    kindHint: kind.hint,
    headings,
    needs,
    stack,
    how,
    manifest,
    dirs: dirs.slice(0, 10),
    files: [...dirs.map(d => d + '/'), ...plainFiles].slice(0, 18),
    fit: fitFor({ ...out, name: repo.name }, query, kind.kind === 'api-service' ? {...ctx,how:'hosted-api'} : ctx),
    steps,
    commands,
    readmeCommands: installCmds,
    deploy: {
      mode: how,
      script: deployScript(out, how, commands),
      notes: how === 'android' ? ['手机 App，不走本地部署', '直接下 APK 安装最简单']
        : how === 'compose' ? ['需要 Docker Desktop 常驻', '端口一般在 docker-compose.yml 里']
        : how === 'docker' ? ['需要 Docker Desktop', '端口看你自己的 -p 参数']
        : ['不需要 Docker', '第一次装依赖会慢一点']
    },
    launch: launchPlan(out, kind.kind, how, commands, releaseAsset),
    estimate: kind.kind === 'api-service' ? '无需本地部署；需配置服务 Key' : kind.kind === 'examples' ? '按所选案例确定' : {
      compose: '约 10 分钟（Docker 已装）',
      docker: '约 10 分钟',
      android: '约 2 分钟（下 APK）',
      python: '约 5~15 分钟（装依赖）',
      'node-dev': '约 5~15 分钟（装依赖）',
      'node-start': '约 5~15 分钟（装依赖）',
      go: '约 3 分钟（编译）',
      rust: '约 10 分钟（首次编译慢）',
      java: '约 10 分钟',
      make: '看作者写没写清楚',
      clone: '不确定，先读 README',
    }[how] || '不确定',
    risks: risks(out, ctx),
    publicFallback: !!publicReader,
    quotaNote: publicReader ? 'GitHub API 配额已用完；已通过公开仓库读取目录和文件并生成使用方案。部分元数据和安装包信息暂不可用。' : tokenPresent() ? '' : '未配置 GitHub Token；仓库文件会缓存复用，公开仓库支持限流后读取。',
    analyzedAt: Date.now()
  };

  onStage('整理成白话');
  for (const [k, v] of cache) if (Date.now() - v.at >= TTL) cache.delete(k);
  if (cache.size >= 100) cache.delete(cache.keys().next().value);
  cache.set(key, { at: Date.now(), data: brief });
  writeDiskCache(key,brief);
  return { ...brief, cached: false };
}


