# Running the eFX Backtester Application

## Prerequisites
- Python 3.11+ with `uv` installed
- Node.js with npm installed

## Quick Start

### 1. Start the Backend Server

Open a PowerShell terminal and run:

```powershell
cd C:\Users\jgehu\QUANT\Projects\nexus\backend\efxbt
uv run uvicorn efxbt.app.main:app --reload
```

The backend will start on **http://127.0.0.1:8000**

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Application startup complete.
```

### 2. Start the Frontend Dev Server

Open a **NEW** PowerShell terminal (keep the backend running) and run:

```powershell
cd C:\Users\jgehu\QUANT\Projects\nexus\frontend
npm run dev
```

The frontend will start on **http://localhost:5173**

You should see:
```
VITE v6.x.x  ready in xxx ms

➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
```

### 3. View the Application

Open your browser and navigate to **http://localhost:5173**

- The **Datasets** page should now show the `sample_efx_2024` dataset
- You should see dataset details including:
  - Version ID
  - Number of pairs, dates, files
  - Trade books (MAD_GLD, MAD_SLV)
  - Market pairs (EURUSD, GBPUSD, USDJPY)
  - Date range (20240101-20240103)

## Troubleshooting

### Backend Issues

**Error: Module not found**
```powershell
cd backend/efxbt
uv sync  # Reinstall dependencies
```

**Error: Port already in use**
- Close any other processes using port 8000
- Or change the port: `uv run uvicorn efxbt.app.main:app --reload --port 8001`

### Frontend Issues

**Error: npm not found**
- Ensure Node.js is installed
- Add npm to your PATH environment variable
- Or use the full path to npm: `C:\Program Files\nodejs\npm.cmd run dev`

**Error: Cannot connect to backend**
- Make sure the backend server is running on port 8000
- Check the browser console for CORS errors
- Verify `vite.config.ts` has the correct proxy settings

**Error: Module not found**
```powershell
cd frontend
npm install  # Reinstall dependencies
```

### No Datasets Showing

If you see "No datasets yet" even though the backend is running:

1. **Check if sample dataset exists:**
   ```powershell
   cd backend/efxbt
   uv run python ../../scripts/create_sample_dataset.py
   ```

2. **Verify backend is returning data:**
   ```powershell
   curl http://127.0.0.1:8000/api/v1/datasets
   ```
   
   Should return JSON array with dataset info.

3. **Check browser console for errors:**
   - Open DevTools (F12)
   - Look for network errors or JavaScript errors
   - Check if the API calls are being made to the correct URL

4. **Verify CORS is working:**
   - The backend should show requests in the terminal
   - Check for CORS errors in browser console

## Development Workflow

1. **Backend changes** - Server auto-reloads (watch for errors in terminal)
2. **Frontend changes** - Vite hot-reloads (check browser console)
3. **Data changes** - Restart backend to pick up new datasets

## API Endpoints Available

### Health
- `GET /api/v1/health` - Backend health check
- `GET /api/v1/health/detailed` - Detailed health with system metrics

### Market Datasets
- `GET /api/v1/datasets` - List all market datasets
- `GET /api/v1/datasets/{name}` - Get dataset details
- `GET /api/v1/datasets/{name}/pairs` - Get dataset pairs
- `GET /api/v1/datasets/{name}/dates` - Get dataset dates
- `GET /api/v1/data-health?dataset={name}` - Get market data health report

### Trade Books
- `GET /api/v1/tradebooks` - List all trade books
- `GET /api/v1/tradebooks/{name}` - Get trade book details
- `GET /api/v1/tradebooks/{name}/pairs` - Get trade book pairs
- `GET /api/v1/tradebooks/{name}/dates` - Get trade book dates
- `GET /api/v1/tradebooks/{name}/health` - Get trade book health report

### Backtest Runs
- `GET /api/v1/runs` - List backtest runs
- `POST /api/v1/runs` - Create new backtest run
- `GET /api/v1/runs/{id}` - Get run details
- `GET /api/v1/runs/{id}/results` - Get run results

### Decrossing
- `POST /api/v1/decross` - Execute trade decrossing

## Notes

- Keep both terminals open while developing
- Use CTRL+C to stop servers
- Frontend connects to backend via Vite proxy (configured in `vite.config.ts`)
- Sample dataset is at: `data/datasets/sample_efx_2024/`
