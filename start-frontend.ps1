# Start Frontend Dev Server
Write-Host "Starting eFX Backtester Frontend..." -ForegroundColor Cyan
Write-Host "Frontend will run on http://localhost:5173" -ForegroundColor Green
Write-Host ""
Write-Host "Make sure the backend is running on port 8000!" -ForegroundColor Yellow
Write-Host "Press CTRL+C to stop the server" -ForegroundColor Yellow
Write-Host ""

Set-Location "C:\Users\jgehu\QUANT\Projects\nexus\frontend"

# Try to find npm
$npmPath = Get-Command npm -ErrorAction SilentlyContinue

if (-not $npmPath) {
    Write-Host "ERROR: npm not found in PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please ensure Node.js is installed and npm is in your PATH" -ForegroundColor Yellow
    Write-Host "Or run manually: cd frontend; npm run dev" -ForegroundColor Yellow
    pause
    exit 1
}

npm run dev
