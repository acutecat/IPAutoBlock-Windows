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

# 版本号：唯一来源是 version.py；同时写入 exe 的文件属性
$version = (& $python -c "import version; print(version.APP_VERSION)").Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "version.py 中的 APP_VERSION 必须是 x.y.z，当前：$version" }
$parts = $version.Split('.')
$quad = "$($parts[0]), $($parts[1]), $($parts[2]), 0"
$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($quad),
    prodvers=($quad),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404b0', [
        StringStruct('CompanyName', 'GK.2'),
        StringStruct('FileDescription', 'IP 自动封锁工具'),
        StringStruct('FileVersion', '$version'),
        StringStruct('InternalName', 'IPAutoBlock'),
        StringStruct('LegalCopyright', 'Copyright © 2025-2026 GK.2'),
        StringStruct('OriginalFilename', 'IPAutoBlock.exe'),
        StringStruct('ProductName', 'IP 自动封锁工具'),
        StringStruct('ProductVersion', '$version'),
        StringStruct('Comments', 'https://github.com/acutecat/IPAutoBlock-Windows')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"@
Set-Content -LiteralPath "$root\build\version_info.txt" -Value $versionInfo -Encoding utf8

# 目标 exe 被运行中的程序占用时，PyInstaller 会在最后一步报 PermissionError；
# 提前检查并给出明确提示。
$outExe = "$root\dist\IPAutoBlock.exe"
if (Test-Path $outExe) {
    try {
        $stream = [System.IO.File]::Open($outExe, 'Open', 'ReadWrite', 'None')
        $stream.Close()
    } catch {
        throw "dist\IPAutoBlock.exe 正在运行，请先从系统托盘退出 IPAutoBlock，再重新打包。"
    }
}

& $python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin `
    --name IPAutoBlock `
    --icon "$root\build\app_icon.ico" `
    --version-file "$root\build\version_info.txt" `
    --add-data "$root\app_icon.png;." `
    --add-data "$root\build\app_icon.ico;." `
    --distpath "dist" `
    --workpath "build\work" `
    --specpath "build" `
    launcher.py

if ($LASTEXITCODE -ne 0) { throw "打包失败" }

Write-Host ""
Write-Host "打包完成：$root\dist\IPAutoBlock.exe"
