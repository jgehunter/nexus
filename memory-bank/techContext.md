# Technical Context: eFX Hedging Backtester

## Technologies Used

### Backend
| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.11+ | Core language |
| FastAPI | 0.128+ | REST API framework |
| Uvicorn | 0.40+ | ASGI server |
| DuckDB | 1.4+ | Embedded SQL, ASOF joins |
| PyArrow | 22+ | Parquet I/O |
| NumPy | 2.3+ | Numerical arrays |
| Numba | 0.63+ | JIT compilation for hot loops |
| Pydantic | 2.12+ | Data validation |
| pydantic-settings | 2.7+ | Configuration management |
| orjson | 3.11+ | Fast JSON serialization |
| psutil | 7.2+ | System metrics |
| Rich | 14.2+ | Logging and formatting |

### Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.3 | UI framework |
| TypeScript | 5.6 | Type safety |
| Vite | 6.0 | Build tool and dev server |
| React Router | 7.1 | Client-side routing |

### Development Tools
| Tool | Purpose |
|------|---------|
| uv | Python package manager |
| pytest | Testing framework |
| pytest-asyncio | Async test support |
| mypy | Static type checking |
| ruff | Linting and formatting |
| httpx | HTTP client for tests |

## Development Setup

### Backend
```bash
cd backend/efxbt
uv sync                                    # Install dependencies
uv run uvicorn efxbt.app.main:app --reload # Start server
uv run pytest tests/ -v                    # Run tests
```

### Frontend
```bash
cd frontend
npm install    # Install dependencies
npm run dev    # Start dev server (port 5173)
npm run build  # Production build
```

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| EFXBT_HOST | 127.0.0.1 | Server bind host |
| EFXBT_PORT | 8000 | Server bind port |
| EFXBT_DEBUG | true | Enable debug mode |
| EFXBT_DATA_ROOT | ../../data | Data directory |
| EFXBT_RESULTS_ROOT | ../../results | Results directory |

## Technical Constraints

### Performance Requirements
- No per-event database queries
- DuckDB batched ASOF joins for market data lookups
- Numba JIT compilation for FIFO matching loops
- ProcessPoolExecutor for parallel shard processing

### Determinism Requirements
- Same inputs + config = identical results
- Stable sorting in all aggregations
- Consistent float handling (avoid non-deterministic operations)

### Platform Requirements
- Windows-compatible (primary development platform)
- No OS-specific system calls
- Standard Python multiprocessing

## Dependencies Graph

```
efxbt
├── fastapi → uvicorn, pydantic
├── duckdb → (standalone)
├── pyarrow → (standalone)
├── numpy → (standalone)
├── numba → numpy
├── pydantic-settings → pydantic
├── orjson → (standalone)
├── psutil → (standalone)
└── rich → (standalone)
```

## API Endpoints

| Endpoint | Method | Status | Description |
|----------|--------|--------|-------------|
| /api/v1/health | GET | ✅ Implemented | Basic health check |
| /api/v1/health/detailed | GET | ✅ Implemented | Detailed health with metrics |
| /api/v1/datasets | GET | ✅ Implemented | List market datasets |
| /api/v1/datasets/{name} | GET | ✅ Implemented | Get dataset details |
| /api/v1/datasets/{name}/pairs | GET | ✅ Implemented | Get dataset pairs |
| /api/v1/datasets/{name}/dates | GET | ✅ Implemented | Get dataset dates |
| /api/v1/tradebooks | GET | ✅ Implemented | List trade books |
| /api/v1/tradebooks/{name} | GET | ✅ Implemented | Get trade book details |
| /api/v1/tradebooks/{name}/dates | GET | ✅ Implemented | Get trade book dates |
| /api/v1/data-health | GET | 🔲 Stub (501) | Data validation |
| /api/v1/decross | * | 🔲 Stub (501) | Decrossing config |
| /api/v1/runs | * | 🔲 Stub (501) | Run management |
| /api/v1/results | * | 🔲 Stub (501) | Results retrieval |
| /api/v1/sweeps | * | 🔲 Stub (501) | Parameter sweeps |
