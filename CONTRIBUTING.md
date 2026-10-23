# 贡献指南

欢迎报告问题、改进中文搜索质量和提交代码。

## 开发环境

按 README 创建 `.venv`、安装 `requirements.txt`，并准备 Node.js 22.21+ 或 24.5+。桌面版入口为 `desktop/run.py`，轻量网页版入口为 `server.mjs`。构建 Windows 包需要额外安装 `requirements-build.txt`。

## 提交问题

请提供版本、Windows 版本、复现步骤、预期行为与实际行为。涉及某个仓库时，附公开仓库链接；涉及网络时，说明代理与错误类型。截图和日志请先遮盖密钥、个人路径及私人仓库信息。

## 提交改动

一次改动聚焦一个问题，说明行为变化与验证方式。不要提交 `.venv`、`dist`、`build`、用户配置、日志、Token 或 API Key。使用离线样例验证网络逻辑，不把个人账号凭据写入测试。

运行 `npm test`；涉及桌面交互时运行 `.\.venv\Scripts\python.exe test\desktop_regression.py`，并运行与改动相关的 Python 测试。完整构建检查由 `build.ps1` 执行，CI 也会运行离线测试。

部署逻辑应从已验证的仓库文件识别入口，不执行 README 中任意文本命令，不覆盖未由本应用管理的目录。AI 输出与规则推断需保留来源及不确定性提示。

提交贡献即表示你有权提供这些内容，并同意按本项目 MIT 许可证分发自己的贡献。
