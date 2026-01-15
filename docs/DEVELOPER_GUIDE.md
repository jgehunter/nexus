# Developer Guide

This guide explains how to extend the Nexus eFX Backtester with new features.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                         │
│   Dashboard │ Datasets │ Trade Books │ Runs │ Results           │
└─────────────────────────────────────────────────────────────────┘
                              │ API
┌─────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                          │
│  ┌─────────┐  ┌─────────────┐  ┌────────────┐  ┌────────────┐  │
│  │ API     │→ │ Services    │→ │ Engine     │→ │ Core       │  │
│  │ routes  │  │ orchestrate │  │ simulate   │  │ data/config│  │
│  └─────────┘  └─────────────┘  └────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    Data Layer (Parquet/DuckDB)                  │
│         datasets/        │        tradebooks/                   │
└─────────────────────────────────────────────────────────────────┘
```

## Adding a New API Endpoint

### 1. Create endpoint handler

```python
# backend/efxbt/src/efxbt/app/api/endpoints/my_feature.py
from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/my-endpoint")
async def get_my_endpoint():
    return {"status": "ok"}

@router.post("/my-endpoint")
async def create_my_endpoint(data: MyInputModel):
    # Implementation
    return {"id": result_id}
```

### 2. Add response models

```python
# backend/efxbt/src/efxbt/app/api/models.py
from pydantic import BaseModel

class MyFeatureResponse(BaseModel):
    id: str
    status: str
```

### 3. Register in router

```python
# backend/efxbt/src/efxbt/app/api/router.py
from .endpoints import my_feature

api_router.include_router(
    my_feature.router,
    prefix="/my-feature",
    tags=["my-feature"],
)
```

### 4. Add tests

```python
# backend/efxbt/tests/app/endpoints/test_my_feature.py
def test_my_endpoint(client):
    response = client.get("/api/v1/my-feature/my-endpoint")
    assert response.status_code == 200
```

## Adding a New Hedging Policy

See [HEDGING_POLICIES.md](./HEDGING_POLICIES.md) for detailed instructions.

Quick summary:

1. Subclass `HedgePolicy` in `engine/shard/hedge_policy.py`
2. Implement `evaluate()` method
3. Register in `POLICY_REGISTRY`
4. Add tests in `tests/engine/test_hedge_policy.py`

## Adding a New KPI Metric

### 1. Define the KPI

```python
# backend/efxbt/src/efxbt/core/kpi/definitions.py
from dataclasses import dataclass

@dataclass
class MyKPI:
    name: str = "my_kpi"
    description: str = "My custom KPI"
    unit: str = "bps"

    def calculate(self, run_results: dict) -> float:
        # Calculation logic
        return value
```

### 2. Register in KPI registry

```python
KPI_REGISTRY["my_kpi"] = MyKPI
```

### 3. Add tests

```python
def test_my_kpi_calculation():
    kpi = MyKPI()
    result = kpi.calculate(sample_results)
    assert result == expected_value
```

## Adding a New Service

Services orchestrate business logic between the API layer and core modules.

### 1. Create service class

```python
# backend/efxbt/src/efxbt/app/services/my_service.py
from pathlib import Path

class MyService:
    def __init__(self, data_root: Path):
        self.data_root = data_root

    def do_something(self, input_data: dict) -> dict:
        # Business logic
        return result
```

### 2. Add to dependency injection

```python
# backend/efxbt/src/efxbt/app/api/deps.py
def get_my_service() -> MyService:
    settings = get_settings()
    return MyService(data_root=Path(settings.data_root))
```

### 3. Use in endpoints

```python
@router.post("/action")
async def do_action(
    data: InputModel,
    service: MyService = Depends(get_my_service),
):
    return service.do_something(data.dict())
```

## Testing Patterns

### Unit Tests

Test individual functions and classes in isolation.

```python
def test_my_function():
    result = my_function(input_value)
    assert result == expected_output
```

### Integration Tests

Test components working together.

```python
# tests/integration/test_my_feature.py
def test_full_workflow(tmp_path, sample_data):
    # Setup
    service = MyService(data_root=tmp_path)

    # Execute
    result = service.run_workflow(sample_data)

    # Verify
    assert result.status == "completed"
    assert (tmp_path / "output.parquet").exists()
```

### API Tests

Test HTTP endpoints with the test client.

```python
def test_endpoint(client):
    response = client.post(
        "/api/v1/my-feature",
        json={"key": "value"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

## Code Style

- **Line length**: 100 characters
- **Python version**: 3.11+
- **Type hints**: Required on all public functions
- **Docstrings**: Google style for public APIs

```python
def my_function(param: str, count: int = 10) -> list[str]:
    """Brief description of function.

    Args:
        param: Description of param
        count: Description of count

    Returns:
        Description of return value

    Raises:
        ValueError: When param is invalid
    """
    pass
```

## Running Quality Checks

```bash
cd backend/efxbt

# Type checking
uv run mypy src/efxbt

# Linting
uv run ruff check src/efxbt

# Format code
uv run ruff format src/efxbt

# Run all tests
uv run pytest tests/ -v
```
