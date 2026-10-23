// 离线单测：仓库解读的判定逻辑（不联网）
import { detectKind, readmeHeadings, readmeCommands, needsOf, usageSteps } from '../lib/analyze.mjs';

let pass = 0, fail = 0;
const t = (name, fn) => {
  try { fn(); pass++; console.log(`  ok   ${name}`); }
  catch (e) { fail++; console.log(`  FAIL ${name}\n       ${e.message}`); }
};
const eq = (a, b, msg) => { if (a !== b) throw new Error(`${msg || ''} 期望 ${b}，实际 ${a}`); };
const ok = (v, msg) => { if (!v) throw new Error(msg || '期望为真'); };

const repo = (over = {}) => ({
  name: 'demo', description: '', topics: [], ...over
});

console.log('类型判定');

t('awesome 清单', () => {
  const k = detectKind(repo({ name: 'awesome-notes', description: 'A curated list of note apps' }), [], null, '');
  eq(k.kind, 'awesome');
  ok(/清单|合集/.test(k.hint));
});

t('提示词合集', () => {
  const k = detectKind(repo({ name: 'jailbreak-prompts', description: '破甲提示词合集' }), [], null, 'prompt injection collection');
  eq(k.kind, 'prompts');
  ok(/不用装/.test(k.hint));
});

t('数据集', () => {
  const k = detectKind(repo({ description: 'A dataset of 15k prompts' }), ['data'], null, '');
  eq(k.kind, 'dataset');
});

t('能跑的服务（compose）', () => {
  const k = detectKind(repo({ description: 'self-hosted notes' }), ['docker-compose.yml'], null, '');
  eq(k.kind, 'app');
});

t('有 start 脚本就是应用', () => {
  const k = detectKind(repo({}), ['package.json'], { type: 'npm', scripts: { start: 'node s.js' } }, '');
  eq(k.kind, 'app');
});

t('有 bin 就是命令行工具', () => {
  const k = detectKind(repo({}), ['package.json'], { type: 'npm', scripts: {}, bin: { x: 'cli.js' } }, '');
  eq(k.kind, 'cli');
});

t('Python 库 vs 命令行', () => {
  const lib = detectKind(repo({}), ['setup.py'], null, 'import it in your code');
  const cli = detectKind(repo({}), ['pyproject.toml'], null, '[project.scripts]\nfoo = "x:main"');
  eq(lib.kind, 'library');
  eq(cli.kind, 'cli');
});

t('看不出类型时说人话', () => {
  const k = detectKind(repo({}), [], null, '');
  eq(k.kind, 'unknown');
  ok(k.hint.length > 10);
});

console.log('README 解析');

const md = `# Title

![badge](x.png)

## Features
- a
### Install
\`\`\`bash
pip install demo
docker run -p 8080:8080 demo
\`\`\`
## Usage
\`\`\`
npm install
\`\`\`
## License
MIT
`;

t('抓得到章节目录', () => {
  const h = readmeHeadings(md);
  ok(h.includes('Features'), '要有 Features');
  ok(h.includes('Usage'), '要有 Usage');
  ok(!h.includes('License'), 'License 不算');
});

t('抓得到安装命令', () => {
  const c = readmeCommands(md);
  ok(c.some(x => x.startsWith('pip install')), '要有 pip');
  ok(c.some(x => x.startsWith('docker run')), '要有 docker');
});

t('需要什么：显卡 / key / 数据库', () => {
  const n = needsOf('Requires CUDA 12 and an OPENAI_API_KEY, plus postgres');
  ok(n.some(x => /显卡/.test(x)));
  ok(n.some(x => /token|key/i.test(x)));
  ok(n.some(x => /数据库/.test(x)));
});

console.log('使用步骤');

t('compose 步骤里有 docker compose up', () => {
  const { steps, commands } = usageSteps('compose', { name: 'demo', html_url: 'https://github.com/a/b', size: 10 }, null, []);
  ok(steps.length >= 3);
  ok(commands.includes('docker compose up -d'));
});

t('python 步骤带虚拟环境', () => {
  const { commands } = usageSteps('python', { name: 'demo', html_url: 'https://github.com/a/demo', size: 10 }, null, ['main.py', 'requirements.txt']);
  ok(commands.some(c => c.includes('venv')));
  ok(commands.includes('.venv\\Scripts\\python.exe main.py'));
});

t('android 不教你部署', () => {
  const { steps } = usageSteps('android', { name: 'demo', html_url: 'u', size: 10 }, null, []);
  ok(steps.some(s => /不用在电脑上/.test(s)));
});

console.log(`\n${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
