// Choose an honest action for the repository type, rather than treating every repo as an app.
export function selectWindowsAsset(assets, full, arch = process.arch) {
  return (assets || []).filter(a => {
    const name = a.name || '', url = a.browser_download_url || '';
    if (!url.startsWith(`https://github.com/${full}/releases/download/`) || !/\.(exe|msi|zip)$/i.test(name)) return false;
    if (/arm64|aarch64/i.test(name) && arch !== 'arm64') return false;
    if (/linux|darwin|macos|osx|android|source[.-]?code/i.test(name)) return false;
    if (/\.zip$/i.test(name) && !/windows|win64|win32|win[-_.]|portable/i.test(name)) return false;
    return Number(a.size || 0) < 2 * 1024 ** 3;
  }).map(a => ({...a, score:(/x64|x86_64|amd64/i.test(a.name) ? 10 : 0) + (/\.exe$/i.test(a.name) ? 30 : /\.msi$/i.test(a.name) ? 25 : 10)}))
    .sort((a,b)=>b.score-a.score)[0] || null;
}

export function launchPlan(repo, kind, how, commands, release = null) {
  const base = { repo:repo.full_name, url:repo.html_url, type:kind };
  if (release) return {...base, mode:'release', title:kind === 'cli' ? '下载命令行工具并查看帮助' : '下载安装包后使用', button:kind === 'cli' ? '一键下载并查看用法' : /\.zip$/i.test(release.name) ? '一键下载并解压' : /setup|install|\.msi$/i.test(release.name) ? '一键下载并打开安装器' : '一键下载并运行',
    description:'使用作者在 GitHub Releases 发布的 Windows 文件，无需自己编译源码。', asset:{name:release.name,url:release.browser_download_url,size:release.size||0,digest:release.digest||null}};
  if (kind === 'examples') return {...base,mode:'examples',title:'挑选一个案例开始',button:'打开所选案例',description:'示例集合按案例使用，先选案例，再核对该案例的依赖和 API 配置。'};
  if (kind === 'api-service') return {...base,mode:'browse',title:'在线 API 接入，无需本地部署',button:'打开接入与 Key 申请说明',description:'当前仓库提供在线 API 接入说明和调用示例，根目录没有可独立部署的服务入口。先申请服务方的 Key，再按说明配置客户端的 API 地址和模型。'};
  if (['awesome','prompts','dataset','plugin'].includes(kind)) return {...base,mode:'browse',title:{awesome:'直接浏览资源目录',prompts:'打开内容，复制使用',dataset:'查看数据与下载说明',plugin:'查看插件安装方式'}[kind],button:'打开使用说明',description:'按这个仓库的内容类型打开相应说明，无需启动统一服务。'};
  const hasEntry = commands.some(c=>/docker compose up|^npm (?:start|run dev)$|python\.exe [^-].*\.py$/.test(c));
  if (commands.length) return {...base, mode:kind === 'library' || !hasEntry ? 'environment' : 'script', title:kind === 'library' || !hasEntry ? '准备可使用的开发环境' : '自动安装并启动', button:kind === 'library' || !hasEntry ? '一键安装开发环境' : '一键部署并启动',description:kind === 'library' ? '自动下载代码并安装依赖；开发库需要在代码中调用，不会伪装成独立应用。' : !hasEntry ? '可以先安装环境，但尚未核验启动入口；安装完成后按 README 的具体命令使用。' : '自动下载代码、安装依赖并执行已识别的入口，过程和错误会显示在应用里。'};
  return {...base,mode:'manual',title:'还需确认使用入口',button:'让 AI 说明怎么用',description:'没有识别到可用安装包或可执行入口。先读取安装说明，避免运行无关命令。'};
}
