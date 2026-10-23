# Windows 自动测试模板

`checks.yml` 包含 Node 与 Python 桌面离线检查，目前作为模板保存，尚未启用 GitHub Actions。

维护者可在 GitHub 网页中把此文件移至 `.github/workflows/checks.yml` 并提交，或使用具备 `workflow` 权限的凭据推送；随后检查 Actions 页的实际运行结果。不要将模板存在视为 CI 已通过。

本地完整检查仍可通过 `build.ps1` 执行。
