"""Test API endpoints for Phase 1.

This script tests the REST API endpoints.
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend" / "efxbt" / "src"
sys.path.insert(0, str(backend_path))

import httpx
from rich.console import Console
from rich.json import JSON


def test_api_endpoints() -> None:
    """Test Phase 1 API endpoints."""
    console = Console()
    base_url = "http://127.0.0.1:8000/api/v1"

    console.print("[bold cyan]Testing Phase 1 API Endpoints[/bold cyan]\n")

    try:
        # Test 1: List datasets
        console.print("[bold]1. GET /api/v1/datasets[/bold]")
        response = httpx.get(f"{base_url}/datasets", timeout=10.0)
        console.print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            console.print(f"Found {len(data)} dataset(s)")
            if data:
                console.print(JSON(str(data[0])))
        console.print()

        # Test 2: Get specific dataset
        if response.status_code == 200 and data:
            dataset_name = data[0]["name"]
            console.print(f"[bold]2. GET /api/v1/datasets/{dataset_name}[/bold]")
            response = httpx.get(f"{base_url}/datasets/{dataset_name}", timeout=10.0)
            console.print(f"Status: {response.status_code}")

            if response.status_code == 200:
                detail = response.json()
                console.print(f"Version ID: {detail['version_id']}")
                console.print(f"Pairs: {len(detail['pairs'])}")
                console.print(f"Dates: {len(detail['dates'])}")
                console.print(f"Pair-dates: {len(detail['pair_dates'])}")
            console.print()

            # Test 3: Get health report
            console.print(
                f"[bold]3. GET /api/v1/data-health?dataset={dataset_name}[/bold]"
            )
            response = httpx.get(
                f"{base_url}/data-health",
                params={"dataset": dataset_name, "validate_schemas": False},
                timeout=30.0,
            )
            console.print(f"Status: {response.status_code}")

            if response.status_code == 200:
                health = response.json()
                console.print(f"Has issues: {health['has_issues']}")
                console.print(f"Total ticks: {health['summary']['total_ticks']:,}")
                console.print(f"Total trades: {health['summary']['total_trades']:,}")
                console.print(f"Tick coverage entries: {len(health['tick_coverage'])}")
                console.print(
                    f"Trade coverage entries: {len(health['trade_coverage'])}"
                )
            console.print()

        console.print("[bold green]✓ All API tests passed![/bold green]")

    except httpx.ConnectError:
        console.print("[bold red]Error: Could not connect to server[/bold red]")
        console.print("Make sure the server is running:")
        console.print("  cd backend/efxbt")
        console.print("  uv run uvicorn efxbt.app.main:app --reload")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")


if __name__ == "__main__":
    test_api_endpoints()
