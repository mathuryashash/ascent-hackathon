#!/usr/bin/env pwsh
# Chimera Dashboard Startup Script (Windows PowerShell)
# This script starts both the backend MCP server and frontend dashboard

$ProjectRoot = "C:\Users\hp\Desktop\ascent hackathon"
$BrainService = Join-Path $ProjectRoot "services\brain\main.py"
$GatewayUI = Join-Path $ProjectRoot "services\gateway_ui\public"

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         Project Chimera - Dashboard Launcher               ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
$pythonCheck = & python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Python not found. Please install Python 3.10+" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Python detected: $pythonCheck" -ForegroundColor Green
Write-Host ""

# Start Brain Service (Backend MCP Server)
Write-Host "🧠 Starting Brain Service (MCP Server on port 8000)..." -ForegroundColor Yellow
Write-Host "   Running: uvicorn services.brain.main:app --host 0.0.0.0 --port 8000 --reload" -ForegroundColor Gray
Write-Host ""

$brainProcess = Start-Process -FilePath "python" `
    -ArgumentList "-m uvicorn services.brain.main:app --host 0.0.0.0 --port 8000 --reload" `
    -WorkingDirectory $ProjectRoot `
    -NoNewWindow `
    -PassThru

Write-Host "✅ Brain Service PID: $($brainProcess.Id)" -ForegroundColor Green
Write-Host "   Wait for: 'Application startup complete'" -ForegroundColor Gray
Write-Host ""

# Wait for backend to start
Start-Sleep -Seconds 3

# Start Frontend Dashboard
Write-Host "🎨 Starting Frontend Dashboard (port 3000)..." -ForegroundColor Yellow
Write-Host "   Running: python -m http.server 3000" -ForegroundColor Gray
Write-Host ""

$gatewayProcess = Start-Process -FilePath "python" `
    -ArgumentList "-m http.server 3000" `
    -WorkingDirectory $GatewayUI `
    -NoNewWindow `
    -PassThru

Write-Host "✅ Frontend Dashboard PID: $($gatewayProcess.Id)" -ForegroundColor Green
Write-Host "   URL: http://localhost:3000" -ForegroundColor Gray
Write-Host ""

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║              🚀 Services Started Successfully!              ║" -ForegroundColor Green
Write-Host "╠════════════════════════════════════════════════════════════╣" -ForegroundColor Green
Write-Host "║                                                            ║" -ForegroundColor Green
Write-Host "║  Backend  (MCP Server): http://localhost:8000/health     ║" -ForegroundColor Green
Write-Host "║  Frontend (Dashboard):  http://localhost:3000            ║" -ForegroundColor Green
Write-Host "║                                                            ║" -ForegroundColor Green
Write-Host "║  📖 Documentation: Read DASHBOARD_SETUP.md                ║" -ForegroundColor Green
Write-Host "║  🧪 Test Alert: POST http://localhost:8000/webhook      ║" -ForegroundColor Green
Write-Host "║                                                            ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

Write-Host "Press Ctrl+C to stop services..." -ForegroundColor Yellow

# Wait for processes
while ($true) {
    Start-Sleep -Seconds 1
    
    # Check if processes are still running
    if (-not (Get-Process -Id $brainProcess.Id -ErrorAction SilentlyContinue)) {
        Write-Host "❌ Brain Service stopped unexpectedly" -ForegroundColor Red
    }
    
    if (-not (Get-Process -Id $gatewayProcess.Id -ErrorAction SilentlyContinue)) {
        Write-Host "❌ Frontend Dashboard stopped unexpectedly" -ForegroundColor Red
    }
}
