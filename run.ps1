# 启动手部追踪（Windows PowerShell）
# 用法：.\run.ps1                    自动挑选可用摄像头
#       .\run.ps1 --camera 1         指定摄像头序号
#       .\run.ps1 --no-connections --dot-radius 8

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# 保证中文输出不乱码
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = "utf-8"

# venv python 写不了系统 %TEMP%，顺手指到项目内，避免偶发的临时文件问题
$tmp = Join-Path $PWD ".pip-tmp"
if (-not (Test-Path $tmp)) { New-Item -ItemType Directory -Force -Path $tmp | Out-Null }
$env:TMPDIR = $tmp
$env:TEMP = $tmp
$env:TMP = $tmp

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "[run] 还没安装依赖，请先运行 .\setup.ps1" -ForegroundColor Red
    exit 1
}

& $py hand_tracker.py @args
exit $LASTEXITCODE
