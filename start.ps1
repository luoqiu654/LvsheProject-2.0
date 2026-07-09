# LvsheProject 3.0 一键启动脚本
# 用法：在项目根目录运行 .\start.ps1
# 前提：已安装 uv、Node.js，.venv 已创建，frontend-next/node_modules 已安装

param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LvsheProject 3.0 启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 检查 .venv
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[错误] 未找到 .venv，请先运行: uv venv && uv pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

# 检查 .env
$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[警告] 未找到 .env 文件，LLM 将不可用！" -ForegroundColor Yellow
    Write-Host "  请复制 .env.example 为 .env 并填入 ZHIPU_API_KEY" -ForegroundColor Yellow
}

# 检查 frontend-next
$FrontendDir = Join-Path $ProjectRoot "frontend-next"
$FrontendNodeModules = Join-Path $FrontendDir "node_modules"
if (-not (Test-Path $FrontendNodeModules)) {
    Write-Host "[警告] frontend-next/node_modules 不存在，正在安装..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    npm.cmd install
    Pop-Location
}

# 启动后端
if (-not $FrontendOnly) {
    Write-Host "`n[1/2] 启动后端 FastAPI (端口 8001)..." -ForegroundColor Green
    $backendCmd = Start-Process -FilePath $VenvPython `
        -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8001" `
        -WorkingDirectory $ProjectRoot `
        -PassThru `
        -WindowStyle Normal
    Write-Host "  后端 PID: $($backendCmd.Id)" -ForegroundColor Gray
    Write-Host "  API 文档: http://127.0.0.1:8001/docs" -ForegroundColor Gray
    Start-Sleep -Seconds 3
}

# 启动前端
if (-not $BackendOnly) {
    Write-Host "`n[2/2] 启动前端 Vite Dev Server (端口 5173)..." -ForegroundColor Green
    $frontendCmd = Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run", "dev" `
        -WorkingDirectory $FrontendDir `
        -PassThru `
        -WindowStyle Normal
    Write-Host "  前端 PID: $($frontendCmd.Id)" -ForegroundColor Gray
    Start-Sleep -Seconds 3
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  启动完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  前端访问: http://localhost:5173" -ForegroundColor White
Write-Host "  后端 API: http://127.0.0.1:8001" -ForegroundColor White
Write-Host "  API 文档: http://127.0.0.1:8001/docs" -ForegroundColor White
Write-Host ""
Write-Host "  按 Ctrl+C 停止服务" -ForegroundColor Gray
Write-Host ""

# 保持窗口运行
try {
    Wait-Process -Id $backendCmd.Id, $frontendCmd.Id
} catch {
    Write-Host "`n服务已停止" -ForegroundColor Yellow
}
