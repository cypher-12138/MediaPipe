# 创建虚拟环境并安装依赖（Windows PowerShell）
# 用法：在终端执行 .\setup.ps1

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# 保证中文输出不乱码
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = "utf-8"

$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "[setup] 正在创建虚拟环境 .venv ..." -ForegroundColor Cyan
    # 优先用 3.12 官方版；注意别用微软商店版 python（它的 pip 访问不了 %TEMP%）
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { python -m venv .venv }
    } else {
        python -m venv .venv
    }
} else {
    Write-Host "[setup] 已存在 .venv，跳过创建。" -ForegroundColor Yellow
}

if (-not (Test-Path $py)) {
    Write-Host "[setup] 虚拟环境创建失败，请确认已安装 Python 3.9~3.12。" -ForegroundColor Red
    exit 1
}

# 关键一步：本机新建的 venv python 写不了系统 %TEMP%，pip 解包时会卡死。
# 把临时目录和缓存都指到项目内，安装就不会卡。
$tmp = Join-Path $PWD ".pip-tmp"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$env:TMPDIR = $tmp
$env:TEMP = $tmp
$env:TMP = $tmp

Write-Host "[setup] 安装 requirements.txt（mediapipe 约 100 MB，请耐心等待）..." -ForegroundColor Cyan
& $py -m pip install --no-input --disable-pip-version-check --no-cache-dir -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[setup] 依赖安装失败，请检查网络或 Python 版本（需 3.9~3.12）。" -ForegroundColor Red
    exit 1
}

Write-Host "[setup] 完成。运行 .\run.ps1 即可。" -ForegroundColor Green
