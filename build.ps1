param([string]$Python = '', [switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location -LiteralPath $root
if (-not $Python) { $Python = Join-Path $root '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python)) { throw '先按 README 创建 .venv 并安装 requirements-build.txt' }
$node = (Get-Command node -ErrorAction Stop).Source
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $root "dist\release-$stamp"
$work = Join-Path $root "build\$stamp"
New-Item -ItemType Directory -Force -Path $out, $work | Out-Null
if (-not $SkipTests) {
    foreach ($test in @('test/selftest.mjs','test/ui-check.mjs','test/analyze_unit.mjs')) {
        & $node $test
        if ($LASTEXITCODE -ne 0) { throw "测试失败: $test" }
    }
    & $node --test test/regression.mjs test/analyze_integration.mjs test/discover_api.mjs test/trending_api.mjs test/launch_plan.mjs test/config_routes.mjs test/network.mjs
    if ($LASTEXITCODE -ne 0) { throw '回归测试失败' }
    & $Python test/test_network_config.py
    if ($LASTEXITCODE -ne 0) { throw "Network configuration tests failed" }
    & $Python test/test_discovery.py
    if ($LASTEXITCODE -ne 0) { throw '推荐模型测试失败' }
    & $Python test/test_project_guide.py
    if ($LASTEXITCODE -ne 0) { throw '项目解读测试失败' }
    & $Python test/test_introductions.py
    if ($LASTEXITCODE -ne 0) { throw '中文简介测试失败' }
    & $Python test/test_release_and_keys.py
    if ($LASTEXITCODE -ne 0) { throw '安装包与密钥测试失败' }
    & $Python test/desktop_regression.py
    if ($LASTEXITCODE -ne 0) { throw '桌面测试失败' }
}
& $Python scripts/make_icon.py
if ($LASTEXITCODE -ne 0) { throw '生成图标失败' }
$argsList = @(
    (Join-Path $root 'desktop\run.py'), '--name', 'IdeaSearch',
    '--windowed', '--onedir', '--noconfirm', '--clean',
    '--runtime-hook', (Join-Path $root 'desktop\rth_log.py'),
    '--version-file', (Join-Path $root 'desktop\version_info.txt'),
    '--icon', (Join-Path $root 'assets\app.ico'),
    '--distpath', $out, '--workpath', $work, '--specpath', $work,
    '--add-data', "$(Join-Path $root 'server.mjs');.",
    '--add-data', "$(Join-Path $root 'config.mjs');.",
    '--add-data', "$(Join-Path $root 'lib');lib",
    '--add-data', "$(Join-Path $root 'public');public",
    '--add-data', "$(Join-Path $root 'assets');assets",
    '--add-binary', "$node;."
)
foreach ($module in @('PySide6.QtQml','PySide6.QtQuick','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtPdf','PySide6.QtMultimedia','PySide6.QtCharts','tkinter','numpy','pytest')) {
    $argsList += @('--exclude-module', $module)
}
# Prevent unrelated PATH entries (e.g. Poppler/Conda) from donating incompatible Qt DLLs.
$savedPath = $env:PATH
$basePython = & $Python -c "import sys; print(sys.base_prefix)"
try {
    $env:PATH = @((Split-Path $Python), $basePython, (Split-Path $node), "$env:WINDIR\System32", $env:WINDIR) -join ';'
    & $Python -m PyInstaller @argsList
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 打包失败' }
} finally {
    $env:PATH = $savedPath
}
$appDir = Join-Path $out 'IdeaSearch'
$exe = Join-Path $appDir 'IdeaSearch.exe'
Copy-Item -LiteralPath (Join-Path $root 'README.md') -Destination (Join-Path $appDir '使用说明.md')
Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination $appDir
Copy-Item -LiteralPath (Join-Path $root '开始使用.txt') -Destination $appDir
Copy-Item -LiteralPath (Join-Path $root 'THIRD_PARTY_NOTICES.md') -Destination $appDir
# Isolated, offline executable smoke test. Never changes the user's shortcut/config.
$oldData = $env:GHF_DATA_DIR
$oldPort = $env:GHF_PORT
$oldQt = $env:QT_QPA_PLATFORM
try {
    $env:GHF_DATA_DIR = Join-Path $work 'smoke-data'
    $env:GHF_PORT = '17989'
    $env:QT_QPA_PLATFORM = 'offscreen'
    $smoke = Start-Process -FilePath $exe -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru
    if (-not $smoke.WaitForExit(30000)) { Stop-Process -Id $smoke.Id; throw '打包应用启动超时' }
    if ($smoke.ExitCode -ne 0) { throw "打包应用自检失败: $($smoke.ExitCode)" }
} finally {
    $env:GHF_DATA_DIR = $oldData
    $env:GHF_PORT = $oldPort
    $env:QT_QPA_PLATFORM = $oldQt
}
$zip = Join-Path $out 'IdeaSearch-2.8.2-win64.zip'
Compress-Archive -LiteralPath $appDir -DestinationPath $zip
& $Python scripts/verify_release.py $zip
if ($LASTEXITCODE -ne 0) { throw 'Relocated release verification failed' }
(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash | Set-Content -LiteralPath "$zip.sha256" -Encoding ascii
$exe | Set-Content -LiteralPath (Join-Path $root 'build\latest-exe.txt') -Encoding utf8
Write-Host "已生成并验证: $exe"
Write-Host "测试包: $zip"
Write-Host '此版本未签名；没有关闭 SmartScreen，也不保证消除信誉提示。'
