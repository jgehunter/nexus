# Start Backend Server
Write-Host "Starting eFX Backtester Backend..." -ForegroundColor Cyan
Write-Host "Backend will run on http://127.0.0.1:8000" -ForegroundColor Green
Write-Host ""
Write-Host "Press CTRL+C to stop the server" -ForegroundColor Yellow
Write-Host ""

Set-Location "C:\Users\jgehu\QUANT\Projects\nexus\backend\efxbt"
uv run uvicorn efxbt.app.main:app --reload
