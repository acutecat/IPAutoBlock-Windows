# 一键打包 IPAutoBlock.exe
# 用法：右键「使用 PowerShell 运行」，或在已安装 PyQt5/PyInstaller 的环境中执行

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Qt 5.15（PyQt5）构建：兼容 Windows 7 SP1 / Server 2008 R2 及以上，
# 不再依赖 Windows 10 才有的系统 ICU（Qt 6 在 Server 2016 上会报 QtCore DLL 加载失败）。
$python = "C:\Users\WorkStation\ipab-qt5\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "未找到打包环境 $python，改用当前 python。"
    $python = "python"
}

& $python -m pip install --disable-pip-version-check "PyQt5==5.15.11" "PyQt5-Qt5>=5.15.2,<5.16" pyinstaller pillow
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }

# 图标：先用 tools\make_ico_from_png.py 从 app_icon.png 生成 build\app_icon.ico
& $python tools\make_ico_from_png.py
if ($LASTEXITCODE -ne 0) { throw "图标生成失败" }

& $python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin `
    --name IPAutoBlock `
    --icon "$root\build\app_icon.ico" `
    --add-data "$root\app_icon.png;." `
    --add-data "$root\build\app_icon.ico;." `
    --distpath "dist" `
    --workpath "build\work" `
    --specpath "build" `
    launcher.py

if ($LASTEXITCODE -ne 0) { throw "打包失败" }

Write-Host ""
Write-Host "打包完成：$root\dist\IPAutoBlock.exe"
