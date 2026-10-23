# 想法搜索 · IdeaSearch

用中文描述需求，发现 GitHub 项目，并在同一窗口阅读用途、运行条件与部署计划。
项目源码使用 MIT 许可证。Windows x64 发布包自带 Python、Qt 和 Node 运行时。

## 主要功能

- **中文找项目**：描述用途，多路检索、合并去重，按语言、星标与更新时间筛选。
- **发现与热榜**：GitHub Trending 日、周、月榜；结合最近搜索与收藏推荐，支持换一批和“不感兴趣”。
- **读懂英文项目**：中文概览、作者原文、AI 用途讲解和仓库问答；支持 DeepSeek 与本机 Ollama。
- **从发现到使用**：按仓库入口提供 Windows 发布包、开发环境、案例或服务部署路线，展示执行日志。
- **整理与比较**：收藏、保存搜索、最多三个项目对比，复制 Markdown 清单。
- **原生桌面体验**：PySide6 界面；Windows 发布包包含 Python、Qt 与 Node，搜索无需另装开发环境。

## 下载与开始

在仓库的 Releases 页面下载 Windows x64 ZIP，**完整解压**后运行 `IdeaSearch/IdeaSearch.exe`。不要只复制 EXE。当前版本 2.8.0，目标平台为 Windows 10/11 x64。

第一次使用可以直接搜索公开项目；GitHub Token 用于提高 API 配额，AI 问答需要单独配置模型。部署第三方项目可能需要 Git、Docker、Node 或 Python，并可能需要服务账号、数据库和 API Key。

> 当前发布包尚未代码签名，Windows 可能显示 SmartScreen 提示。开源本身不会消除该提示。

## 已有基础能力

- 搜索、项目详情与部署输出在同一窗口；详情页可返回搜索并保留结果。
- 搜索可以取消；页面退出时中止网络请求。重复启动激活已有窗口。
- 原生 Windows GUI 打包，不依赖 VBS 隐藏控制台，不修改系统安全设置。
- 修复英文分词、短语言名误判、否定条件、语言覆盖及误去重。
- 双链等能力保留为待核验条件；搜索命中不等于已经验证功能。
- 部署只使用依据项目文件生成的模板；README 示例不进入执行脚本。
- Python 用虚拟环境解释器安装；Node 先构建再启动；命令失败立即停止。
- 运行环境显示“缺少 / 尚未核验”，不以星标或检测不到问题保证能运行。

## 运行源码（Windows）

需要 Python 3.10～3.14、Node.js 22.21+ 或 24.5+（打包版自带 Node）。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe desktop\run.py
```

也可以独立运行网页版：`node server.mjs`，打开 http://127.0.0.1:7788。
桌面版仅监听本机；优先使用 127.0.0.1:17890，占用时自动选择空闲端口。可通过 GHF_PORT 指定桌面引擎端口。

## Token 与 AI 配置

- GitHub 设置：填写 GitHub 生成的只读 Token，点“测试 GitHub 连接”，再保存。公开仓库可不填，但未登录 API 配额有限。
- AI 设置：选 DeepSeek，基础地址 https://api.deepseek.com，填写平台生成的 Key，点“测试连接 / 读取模型”，选择可用模型后保存。
- 密钥只填 Key 本身，不要带 Bearer 前缀。GitHub 与 DeepSeek 的密钥不通用。
- 模型列表测试证明接口和认证可用；实际问答仍可能受余额或流量限制。

## 测试与打包

```powershell
npm test
.\.venv\Scripts\python.exe test\test_discovery.py
.\.venv\Scripts\python.exe test\desktop_regression.py
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File build.ps1
```

最后一条命令的 ExecutionPolicy 仅作用于这次构建进程，不修改系统永久策略。
构建产物在 dist/release-时间/IdeaSearch/，双击 IdeaSearch.exe。
整个目录必须一起移动。构建会执行离线回归和 exe 自检，失败则停止。
不会替换原版，不会自动修改桌面快捷方式，不会发布 GitHub 仓库。

## 使用与边界

搜索需要网络访问 GitHub 官方 API；热度榜读取 github.com/trending 的公开页面。
可选择本机 Ollama 或 DeepSeek API 用于中文简述和仓库问答；用途问题在模型不可用时明确提示，其他简单问题可用资料规则回答。
AI 输出可能有误，卡片保留作者原文供核对。中文简述将项目名称与简介发送到选择的模型服务；DeepSeek 会产生对应 API 用量。
GitHub 热度榜不是自行按创建日期拼出的榜单，周期新增星标直接使用来源页面的数值。
页面结构变化、访问限制或网络失败会提示；存在快照时保留上次数据及时间，不能据此视为实时榜单。

主检索为词典和规则，不是完整的语义理解。否定条件只支持已列出的常见技术词。
功能要求目前依据仓库元数据标注，仍需检查 README 或实际运行确认。
“上升期”是星标与项目年龄的近似比值，不是最近新增星标数据。
未知构建方式、Dockerfile 端口未知、其他包管理器等情况不猜测自动部署。
首次部署会克隆到 %USERPROFILE%/ghf-deploy；未标记为本应用管理的目录不会覆盖或自动更新；匹配本应用标记的目录可重复安装依赖，但不重置或拉取覆盖源码。
离开详情页会停止前台部署进程；后台容器、数据卷和外部服务需按项目文档单独管理。

## 数据与诊断

推荐使用 GitHub 公开仓库数据，最多缓存 300 个候选；搜索兴趣、收藏和“不感兴趣”保存在本机。
近期搜索权重更高；收藏的主题和语言会影响排序，卡片显示推荐原因。这是可解释的本地规则排序。
项目中文概览按项目类型与已读取资料中的主题生成；原文可展开核对，不等同于全文翻译。
切换探索方向会请求 GitHub API；候选不足时，“换一批”会获取下一页，网络失败保留已有推荐。
重置兴趣会清除搜索兴趣与屏蔽列表，收藏保留并继续影响推荐；项目对比在本次运行期间保留。

默认配置：~/.github-finder.json（Token 为本地明文，请保护用户目录）
历史/收藏：~/.github-finder-desktop.json
可通过 GHF_DATA_DIR 为测试指定独立配置目录。
启动日志：%TEMP%/ghf-start.log 与 %TEMP%/ghf-stdout.log。
本机环境清单不发送到 DeepSeek；远程问答只使用仓库资料、问题及相关对话。
AI Key：~/.github-finder-ai-key.json，使用 Windows DPAPI 按当前用户加密；环境变量 DEEPSEEK_API_KEY 也可使用。
仓库解读缓存：~/.github-finder-analysis-cache.json，正常有效期 30 分钟，连接失败时可展示 24 小时内快照。

## Windows 提示说明

SmartScreen 根据下载来源、文件/发布者信誉等判断。原生窗口应用仍可能出现提示。
此预览版没有发布者签名。改界面、开源或换安装器不会自动获得信誉。
正式分发前需要选择签名或商店发布流程；签名也不保证首次发布没有信誉提示。
不建议关闭系统保护或把程序整体加入排除列表。
官方说明：https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation

## 尚未完成

- 用户体验验收、更多真实需求的搜索质量评估。
- 发布者签名和正式安装包。
- Linux 与 macOS 的桌面打包和兼容性验证。

## 分发与首次使用

- 目标平台：Windows 10/11 x64；其他系统尚未验证。
- 完整解压 win64.zip，打开 IdeaSearch/IdeaSearch.exe；不要只复制 EXE。
- 搜索不需要预装 Python、Node、Git 或 Ollama；网络功能需要能访问 GitHub。
- AI 需用户自行配置 DeepSeek Key 或安装运行 Ollama 和模型；发布包不含作者账号。
- GitHub Token 和 AI Key 分开配置。Token 可提高 API 配额；公开文件回退仍受网络与仓库类型限制。
- 部署项目可能需要 Git、Docker 等环境，服务账号和数据库需按项目要求配置。
- 配置和缓存保存在当前用户目录。加密 Key 换电脑或 Windows 用户后需重新配置。
- 尚未代码签名，可能出现 SmartScreen 提示。
- MIT 适用于项目自有代码；依赖授权见 THIRD_PARTY_NOTICES.md。

## 项目结构

| 目录 | 职责 |
| --- | --- |
| `desktop/` | PySide6 界面、配置、问答与部署交互 |
| `lib/` | GitHub 检索、仓库分析、热榜与部署计划 |
| `public/` | 轻量网页版界面 |
| `test/` | 离线逻辑与桌面回归测试 |
| `scripts/` | 图标生成及发布包验证 |

## 参与与许可

欢迎提交问题和改进，参见 [贡献指南](CONTRIBUTING.md)、[安全说明](SECURITY.md) 和 [更新记录](CHANGELOG.md)。提交日志前请删除 Token、API Key、个人路径和私人仓库信息。

项目自有源码采用 [MIT](LICENSE)，允许商用、修改和再分发。Qt、Python、Node 等依赖保留各自授权，参见 [第三方声明](THIRD_PARTY_NOTICES.md)。
