// Only commands derived from verified repository files enter executable plans.
// README examples are displayed separately and are never appended to scripts.
export function usageSteps(how, repo, manifest, files) {
  const steps = ['核对项目 README 中的平台、版本和配置要求。'];
  const commands = [];
  if (how === 'android') return { steps: ['这是手机 App，不用在电脑上部署。', '打开 Releases 核对版本和来源后下载。'], commands };
  if (!/^[\w.-]+$/.test(repo.name || '') || !/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/.test(repo.html_url || '')) return { steps, commands };
  commands.push(`git clone ${repo.html_url}.git`, `cd ${repo.name}`);
  if (how === 'compose') commands.push('docker compose config --quiet', 'docker compose up -d');
  else if (how === 'python') {
    commands.push('python -m venv .venv');
    const py = '.venv\\Scripts\\python.exe';
    if (files.includes('requirements.txt')) commands.push(`${py} -m pip install -r requirements.txt`);
    else if (files.includes('pyproject.toml') || files.includes('setup.py')) commands.push(`${py} -m pip install .`);
    const entry = ['main.py', 'app.py', 'run.py', 'server.py'].find(f => files.includes(f));
    if (entry) commands.push(`${py} ${entry}`);
    else steps.push('未确认启动入口；安装完成后按 README 使用，不能假定运行 main.py。');
  } else if (how === 'node-start' || how === 'node-dev') {
    const manager = manifest?.packageManager || '';
    if ((manager && !manager.startsWith('npm@')) || files.some(f => ['pnpm-lock.yaml', 'yarn.lock', 'bun.lock', 'bun.lockb'].includes(f))) {
      return { steps: [...steps, '项目使用其他包管理器，请按 README 安装；暂不生成自动部署脚本。'], commands: [] };
    }
    commands.push(files.includes('package-lock.json') ? 'npm ci' : 'npm install');
    if (manifest?.scripts?.build) commands.push('npm run build');
    if (manifest?.scripts?.start) commands.push('npm start');
    else if (manifest?.scripts?.dev) commands.push('npm run dev');
    else return { steps: [...steps, '没有已声明的启动脚本，请按 README 使用。'], commands: [] };
  } else {
    return { steps: [...steps, '尚不能确定完整部署方案。请打开仓库阅读安装说明。'], commands: [] };
  }
  steps.push('克隆仓库并进入独立目录。', '按下方命令安装和启动，任何一步失败都会停止。');
  return { steps, commands };
}

export function deployScript(repo, how, commands) {
  if (!commands.length || how === 'android' || !/^[\w.-]+\/[\w.-]+$/.test(repo.full_name || '')) return '';
  const lines = ['@echo off', 'setlocal', 'chcp 65001 >nul', `set "TARGET=%USERPROFILE%\\ghf-deploy\\${repo.full_name.replace('/', '_')}"`,
    'where git >nul 2>nul || exit /b 1'];
  const runtime = how === 'compose' ? 'docker' : how === 'python' ? 'python' : 'node';
  lines.push(`where ${runtime} >nul 2>nul || exit /b 1`,
    // Reuse only our own matching project; never reset or pull over user changes.
    'if exist "%TARGET%" (',
    '  if not exist "%TARGET%\\.idea-search-managed" (echo Existing folder is not managed by IdeaSearch. & exit /b 1)',
    `  findstr /x /l /c:"${repo.full_name}" "%TARGET%\\.idea-search-managed" >nul || exit /b 1`,
    ') else (',
    `git clone --depth 1 https://github.com/${repo.full_name}.git "%TARGET%"`,
    'if errorlevel 1 exit /b 1',
    `echo ${repo.full_name}>"%TARGET%\\.idea-search-managed"`,
    ')', 'cd /d "%TARGET%"', 'if errorlevel 1 exit /b 1');
  for (const c of commands.filter(c => !c.startsWith('git clone ') && !c.startsWith('cd '))) {
    // All commands here are our templates. CALL returns from npm.cmd on Windows.
    lines.push(c.startsWith('npm ') ? `call ${c}` : c, 'if errorlevel 1 exit /b 1');
  }
  lines.push('exit /b 0');
  return lines.join('\r\n');
}
