import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
process.env.GHF_DATA_DIR = mkdtempSync(join(tmpdir(),'idea-search-analysis-test-'));
const { analyzeRepo, relevantReadme } = await import('../lib/analyze.mjs');
const { parsePublicRepo } = await import('../lib/public-repo.mjs');
const revision='a'.repeat(40);
const publicPage = (full, names) => `<script type="application/json" data-target="react-app.embeddedData">${JSON.stringify({payload:{
  codeViewRepoRoute:{path:'/',refInfo:{currentOid:revision},tree:{items:names.map(name=>({name,path:name,contentType:'file'})),totalCount:names.length}},
  codeViewLayoutRoute:{repo:{name:full.split('/')[1],ownerLogin:full.split('/')[0],public:true,private:false,defaultBranch:'main'}},
  sidebarAbout:{description:'A sample web app',topics:[],stargazerCount:10,repo:{license:{spdxId:'MIT'}}}
}})}</script>`;

test('exhausted API quota falls back to verified public files and retains one-click deployment', async () => {
  const previous=globalThis.fetch, calls=[];
  globalThis.fetch=async url=>{
    calls.push(url);
    if (url.startsWith('https://api.github.com/')) return new Response('{"message":"API rate limit exceeded"}',{status:403,headers:{'x-ratelimit-remaining':'0'}});
    if (url==='https://github.com/fixture/public-app') return new Response(publicPage('fixture/public-app',['README.md','package.json','compose.yml']));
    assert.ok(url.startsWith(`https://raw.githubusercontent.com/fixture/public-app/${revision}/`));
    return new Response(url.endsWith('/package.json') ? JSON.stringify({scripts:{start:'node app.js'}}) : '# Web app\n\nA web app for collecting notes and files.\n\n```bash\nnpm install example && echo UNTRUSTED\n```');
  };
  try {
    const result=await analyzeRepo('fixture/public-app');
    assert.equal(result.publicFallback,true);
    assert.equal(result.launch.mode,'script');
    assert.equal(result.launch.button,'一键部署并启动');
    assert.match(result.deploy.script,/docker compose up -d/);
    assert.doesNotMatch(result.deploy.script,/UNTRUSTED/);
    assert.equal(calls.filter(u=>u.startsWith('https://api.github.com/')).length,1);
    assert.match(result.quotaNote,/公开仓库/);
  } finally {globalThis.fetch=previous;}
});

test('public reader rejects login pages, repo mismatches and unverified revisions',()=>{
  assert.throws(()=>parsePublicRepo('<html>Sign in</html>','fixture/app'),/验证公开仓库/);
  assert.throws(()=>parsePublicRepo(publicPage('fixture/other',['compose.yml']),'fixture/app'),/验证公开仓库/);
  assert.throws(()=>parsePublicRepo(publicPage('fixture/app',['compose.yml']).replace(revision,'main'),'fixture/app'),/版本/);
  const data=parsePublicRepo(publicPage('fixture/app',['package.json','../compose.yml']),'fixture/app');
  assert.deepEqual(data.entries.map(e=>e.name),['package.json']);
  assert.equal(data.repo.license.spdx_id,'MIT');
});

test('hosted API documentation offers connection guidance instead of a fake deployment', async()=>{
  const original=globalThis.fetch;
  globalThis.fetch=async url=>{
    if(url.startsWith('https://api.github.com/'))return new Response('{"message":"API rate limit exceeded"}',{status:403,headers:{'x-ratelimit-remaining':'0'}});
    if(url==='https://github.com/fixture/api-docs')return new Response(publicPage('fixture/api-docs',['README.md','LICENSE']).replace('A sample web app','免费大模型API，支持免费调用模型'));
    return new Response('# Free API\n\n注册并绑定Github免费使用。该API Key用于转发API，需要配置转发Host。');
  };
  try{
    const d=await analyzeRepo('fixture/api-docs');
    assert.equal(d.kind,'api-service');assert.equal(d.launch.mode,'browse');
    assert.match(d.launch.button,/Key 申请/);assert.match(d.steps.join(' '),/客户端/);
    assert.equal(d.deploy.script,'');assert.deepEqual(d.commands,[]);
    assert.doesNotMatch(d.fit.reasons.join(' '),/作者没写构建/);
  }finally{globalThis.fetch=original;}
});

test('API file reads are reused when the search question changes',async()=>{
  const previous=globalThis.fetch;let calls=0;
  globalThis.fetch=async url=>{
    calls++;
    const data=url.endsWith('/readme') ? {content:Buffer.from('# Library\n\nA small package for processing text.').toString('base64')} : url.endsWith('/contents/') ? [{name:'pyproject.toml',type:'file'}] : {name:'reuse',full_name:'fixture/reuse',html_url:'https://github.com/fixture/reuse',description:'A Python library',topics:[]};
    return new Response(JSON.stringify(data));
  };
  try {
    await analyzeRepo('fixture/reuse','first query');const first=calls;
    await analyzeRepo('fixture/reuse','different query');
    assert.equal(calls,first);assert.equal(first,3);
  }finally{globalThis.fetch=previous;}
});

test('README examples never become executable commands; manifest fields survive', async () => {
  const originalFetch = globalThis.fetch;
  const repo = { full_name: 'fixture/app', name: 'app', html_url: 'https://github.com/fixture/app',
    description: 'A sample app', stargazers_count: 10, pushed_at: new Date().toISOString(), topics: [] };
  const content = text => ({ content: Buffer.from(text).toString('base64') });
  globalThis.fetch = async url => {
    let data = repo;
    if (url.endsWith('/readme')) data = content('# Demo\n\nAn application for testing a deployment plan.\n\n```bash\nnpm install demo && echo UNTRUSTED_EXAMPLE\n```');
    else if (url.endsWith('/contents/')) data = ['package.json', 'compose.yml'].map(name => ({ name, type: 'file' }));
    else if (url.endsWith('/contents/package.json')) data = content(JSON.stringify({ scripts: { dev: 'vite', start: 'node app.js' }, bin: { app: './cli.js' }, engines: { node: '>=22' } }));
    return new Response(JSON.stringify(data), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  try {
    const result = await analyzeRepo('fixture/app');
    assert.equal(result.how, 'compose');
    assert.deepEqual(result.manifest.bin, { app: './cli.js' });
    assert.match(result.readmeCommands.join(' '), /UNTRUSTED_EXAMPLE/);
    assert.doesNotMatch(result.deploy.script, /UNTRUSTED_EXAMPLE/);
    assert.doesNotMatch(result.commands.join(' '), /UNTRUSTED_EXAMPLE/);
    assert.notEqual(result.fit.level, 'good');
  } finally { globalThis.fetch = originalFetch; }
});

test('cookbook with setup.py is a tutorial collection without a generated launch script', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async url => {
    let data = { full_name: 'fixture/claude-cookbooks', name: 'claude-cookbooks', html_url: 'https://github.com/fixture/claude-cookbooks',
      description: 'Code and guides with examples for developers', topics: [], stargazers_count: 100 };
    if (url.endsWith('/readme')) data = { content: Buffer.from('# Claude Cookbooks\n\nCode examples and guides.\n\n## Sponsors\nPartner has vision agents.\n\n## Tool use\nLearn to call functions.').toString('base64') };
    else if (url.endsWith('/contents/')) data = [{ name: 'setup.py', type: 'file' }, { name: 'tool_use', type: 'dir' }];
    return new Response(JSON.stringify(data), { status: 200 });
  };
  try {
    const d = await analyzeRepo('fixture/claude-cookbooks');
    assert.equal(d.kind, 'examples');
    assert.deepEqual(d.commands, []);
    assert.equal(d.deploy.script, '');
    assert.match(d.steps.join(' '), /案例|Notebook/);
    assert.doesNotMatch(d.readme, /Partner|Sponsors/);
    assert.match(d.readme, /Tool use/);
  } finally { globalThis.fetch = originalFetch; }
});

test('advertising section removal resumes at the next peer heading', () => {
  const result = relevantReadme('# App\nIntro\n## 感谢赞助商\nvision\n### Partner\nagents\n## 功能\n会话管理');
  assert.doesNotMatch(result, /vision|agents/);
  assert.match(result, /会话管理/);
});

test('analysis survives module reload without consuming GitHub API quota again',async()=>{
  const reload=await import('../lib/analyze.mjs?disk-cache-verification');
  const fetchBefore=globalThis.fetch;
  globalThis.fetch=()=>{throw new Error('network should not be used');};
  try {
    const data=await reload.analyzeRepo('fixture/app');
    assert.equal(data.diskCached,true); assert.equal(data.full_name,'fixture/app');
  }finally{globalThis.fetch=fetchBefore;}
});

test('desktop app prefers an author release and Python library installs the package',async()=>{
  const originalFetch=globalThis.fetch;
  globalThis.fetch=async url=>{
    const desktop=url.includes('/desktop');
    const name=desktop?'desktop':'pythonlib';
    let data={name,full_name:'fixture/'+name,html_url:'https://github.com/fixture/'+name,description:desktop?'A desktop application':'A Python library',topics:[],stargazers_count:20};
    if(url.endsWith('/readme'))data={content:Buffer.from(desktop?'Desktop application for Windows.':'Import this library in your code.').toString('base64')};
    else if(url.endsWith('/contents/'))data=(desktop?['src-tauri']:['pyproject.toml']).map(name=>({name,type:'file'}));
    else if(url.endsWith('/releases/latest'))data={assets:[{name:'desktop-x64-setup.exe',size:100,browser_download_url:'https://github.com/fixture/desktop/releases/download/v1/desktop-x64-setup.exe'}]};
    return new Response(JSON.stringify(data),{status:200});
  };
  try{
    const app=await analyzeRepo('fixture/desktop');assert.equal(app.launch.mode,'release');assert.equal(app.kind,'desktop');
    const library=await analyzeRepo('fixture/pythonlib');assert.equal(library.launch.mode,'environment');assert.match(library.commands.join(' '),/pip install \./);assert.doesNotMatch(library.commands.join(' '),/main\.py/);
  }finally{globalThis.fetch=originalFetch;}
});
