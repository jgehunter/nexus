# Start Both Backend and Frontend Servers
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  eFX Backtester - Starting Servers" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Start Backend in new window
Write-Host "1. Starting Backend Server..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$PSScriptRoot\start-backend.ps1"

# Wait a bit for backend to start
Start-Sleep -Seconds 3

# Start Frontend in new window
Write-Host "2. Starting Frontend Server..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$PSScriptRoot\start-frontend.ps1"

Write-Host ""
Write-Host "Success! Both servers starting..." -ForegroundColor Green
Write-Host ""
Write-Host "Backend:  http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "Open your browser and navigate to http://localhost:5173" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press any key to close this window..."
Read-Host
