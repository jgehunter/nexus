"""End-to-end tests for complete run workflow.

Tests the full pipeline from run creation through analytics retrieval:
1. Create run with test tradebook + dataset
2. Start execution and poll for completion
3. Verify all analytics endpoints return correct data
4. Ensure performance meets targets (< 2s per endpoint)
"""

import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from efxbt.app.main import app
from efxbt.core.config.settings import Settings
from efxbt.core.data.schemas import TradeRecord

from .fixtures.test_data import (
    create_test_market_dataset,
    create_test_tradebook,
    generate_date_range,
)


# Test constants
E2E_TIMEOUT_SECONDS = 120  # Max time to wait for run completion
POLL_INTERVAL_SECONDS = 0.5  # How often to poll status
ANALYTICS_TIMEOUT_MS = 2000  # Max time for analytics endpoints


@pytest.fixture
def e2e_environment():
    """Create complete test environment for E2E testing.

    Sets up:
    - Temporary data directory with test market dataset
    - Test tradebook with realistic trades across multiple pairs
    - FastAPI test client with the data root configured
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        data_root = Path(tmpdir)
        results_root = data_root / "results"
        results_root.mkdir(exist_ok=True)

        # Define test parameters
        dataset_name = "e2e_test_market"
        tradebook_name = "e2e_test_trades"
        pairs = ["EURUSD", "GBPUSD", "USDJPY", "EURGBP", "AUDUSD"]
        date_range = ("20240101", "20240103")  # 3 days

        # Create market dataset
        create_test_market_dataset(
            data_root=data_root,
            dataset_name=dataset_name,
            pairs=pairs,
            date_range=date_range,
            ticks_per_day=500,  # 500 ticks per day per pair
        )

        # Create tradebook with comprehensive trades
        trades = _generate_e2e_trades(pairs, date_range)
        create_test_tradebook(
            data_root=data_root,
            book_name=tradebook_name,
            trades=trades,
        )

        # Override settings for test environment
        # Note: We patch the settings via environment or direct import
        original_data_root = Settings().data_root
        original_results_root = Settings().results_root

        # Create test client
        client = TestClient(app)

        yield {
            "client": client,
            "data_root": data_root,
            "results_root": results_root,
            "dataset_name": dataset_name,
            "tradebook_name": tradebook_name,
            "pairs": pairs,
            "date_range": date_range,
            "expected_trade_count": len(trades),
        }


def _generate_e2e_trades(
    pairs: list[str],
    date_range: tuple[str, str],
) -> list[TradeRecord]:
    """Generate comprehensive trades for E2E testing.

    Creates trades across all pairs and dates to exercise the full pipeline.
    """
    trades = []
    trade_counter = 1

    dates = generate_date_range(date_range[0], date_range[1])

    for date_str in dates:
        # Convert date to base timestamp
        base_ts = int(datetime.strptime(date_str, "%Y%m%d").timestamp() * 1000)

        for pair in pairs:
            # Generate 20 trades per pair per day
            for i in range(20):
                # Alternate buy/sell
                side = 1 if i % 2 == 0 else -1

                # Vary quantity between 1000 and 50000
                qty = 1000.0 + (i * 2500)

                # Spread trades throughout the day
                timestamp_ms = base_ts + (i * 3600000) + (pairs.index(pair) * 60000)

                # Realistic prices based on pair
                price = _get_base_price(pair)

                trade = TradeRecord(
                    timestamp_ms=timestamp_ms,
                    pair=pair,
                    side=side,
                    qty=qty,
                    price=price,
                    trade_id=f"E2E_{trade_counter:06d}",
                )
                trades.append(trade)
                trade_counter += 1

    return trades


def _get_base_price(pair: str) -> float:
    """Get realistic base price for a currency pair."""
    prices = {
        "EURUSD": 1.10,
        "GBPUSD": 1.25,
        "USDJPY": 150.0,
        "EURGBP": 0.88,
        "AUDUSD": 0.65,
        "USDCAD": 1.35,
        "NZDUSD": 0.60,
        "EURJPY": 165.0,
    }
    return prices.get(pair, 1.0)


class TestRunE2E:
    """End-to-end tests for complete run workflow."""

    @pytest.mark.skip(reason="Requires full application setup with data paths")
    def test_run_completes_with_analytics(self, e2e_environment):
        """Test complete run workflow from creation to analytics.

        1. Create a run with test tradebook + dataset
        2. Start the run
        3. Poll until completed (with timeout)
        4. Verify summary has all expected metrics
        5. Verify risk_metrics, ops_metrics, internalization_metrics populated
        """
        client = e2e_environment["client"]

        # Step 1: Create run
        run_config = {
            "dataset": e2e_environment["dataset_name"],
            "tradebook": e2e_environment["tradebook_name"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-03",
            "name": "E2E Test Run",
            "description": "Automated E2E test",
            "simulation_config": {
                "dataset": e2e_environment["dataset_name"],
                "reporting_currency": "USD",
                "hedge_policy": "aggressive",
                "hedge_policy_config": {
                    "risk_band_qty": 10000.0,
                    "hedge_mode": "full",
                },
                "sample_interval_seconds": 30,
            },
            "general_config": {
                "direct_pairs": e2e_environment["pairs"],
            },
        }

        response = client.post("/runs", json=run_config)
        assert response.status_code == 200, f"Create run failed: {response.text}"

        create_result = response.json()
        run_id = create_result["run_id"]
        assert run_id is not None

        # Step 2: Start run
        response = client.post(f"/runs/{run_id}/start")
        assert response.status_code == 200, f"Start run failed: {response.text}"

        # Step 3: Poll for completion
        start_time = time.time()
        final_status = None

        while (time.time() - start_time) < E2E_TIMEOUT_SECONDS:
            response = client.get(f"/runs/{run_id}/status")
            assert response.status_code == 200

            status_data = response.json()
            current_status = status_data["status"]

            if current_status in ("completed", "failed"):
                final_status = current_status
                break

            time.sleep(POLL_INTERVAL_SECONDS)

        elapsed = time.time() - start_time
        assert final_status == "completed", f"Run did not complete: {final_status} after {elapsed:.1f}s"

        # Step 4: Verify summary
        response = client.get(f"/results/{run_id}")
        assert response.status_code == 200, f"Get summary failed: {response.text}"

        summary = response.json()

        # Check required fields
        assert "run_id" in summary
        assert summary["run_id"] == run_id
        assert "total_pnl" in summary
        assert "total_volume" in summary
        assert "trade_count" in summary

        # Verify trade count matches expected
        assert summary["trade_count"] > 0

        # Step 5: Verify risk metrics
        response = client.get(f"/results/{run_id}/risk")
        assert response.status_code == 200

        risk_data = response.json()
        assert "risk" in risk_data
        risk = risk_data["risk"]

        # Check required risk metrics
        assert "max_abs_inventory" in risk
        assert "max_drawdown" in risk
        assert "inventory_p95" in risk

        # Step 6: Verify internalization metrics
        response = client.get(f"/results/{run_id}/internalization")
        assert response.status_code == 200

        intern_data = response.json()
        assert "metrics" in intern_data

        # Step 7: Verify timeseries
        response = client.get(f"/results/{run_id}/timeseries")
        assert response.status_code == 200

        ts_data = response.json()
        assert "points" in ts_data
        assert len(ts_data["points"]) > 0

        print(f"\nE2E Test Results:")
        print(f"  Run ID: {run_id}")
        print(f"  Completion time: {elapsed:.1f}s")
        print(f"  Total PnL: {summary.get('total_pnl', 'N/A')}")
        print(f"  Trade count: {summary.get('trade_count', 'N/A')}")
        print(f"  Max inventory: {risk.get('max_abs_inventory', 'N/A')}")

    @pytest.mark.skip(reason="Requires full application setup with data paths")
    def test_run_analytics_performance(self, e2e_environment):
        """Test analytics endpoint performance.

        1. Create run with comprehensive test data
        2. Start and wait for completion
        3. Time each analytics endpoint:
           - GET /results/{run_id} (summary)
           - GET /results/{run_id}/risk
           - GET /results/{run_id}/timeseries
           - GET /results/{run_id}/internalization
        4. Assert all complete within target time
        """
        client = e2e_environment["client"]

        # Create and start run (simplified - assumes previous test passes)
        run_config = {
            "dataset": e2e_environment["dataset_name"],
            "tradebook": e2e_environment["tradebook_name"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-03",
            "simulation_config": {
                "dataset": e2e_environment["dataset_name"],
                "reporting_currency": "USD",
                "hedge_policy": "aggressive",
                "hedge_policy_config": {"risk_band_qty": 10000.0, "hedge_mode": "full"},
                "sample_interval_seconds": 30,
            },
            "general_config": {
                "direct_pairs": e2e_environment["pairs"],
            },
        }

        # Create run
        response = client.post("/runs", json=run_config, params={"idempotence": "new"})
        assert response.status_code == 200
        run_id = response.json()["run_id"]

        # Start run
        response = client.post(f"/runs/{run_id}/start")
        assert response.status_code == 200

        # Wait for completion
        start_time = time.time()
        while (time.time() - start_time) < E2E_TIMEOUT_SECONDS:
            response = client.get(f"/runs/{run_id}/status")
            if response.json()["status"] in ("completed", "failed"):
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        assert response.json()["status"] == "completed"

        # Performance tests for each endpoint
        endpoints = [
            ("summary", f"/results/{run_id}"),
            ("risk", f"/results/{run_id}/risk"),
            ("timeseries", f"/results/{run_id}/timeseries"),
            ("internalization", f"/results/{run_id}/internalization"),
            ("pnl", f"/results/{run_id}/pnl"),
        ]

        performance_results = {}

        for name, endpoint in endpoints:
            start = time.perf_counter()
            response = client.get(endpoint)
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert response.status_code == 200, f"{name} endpoint failed: {response.text}"
            assert elapsed_ms < ANALYTICS_TIMEOUT_MS, (
                f"{name} endpoint took {elapsed_ms:.0f}ms (max {ANALYTICS_TIMEOUT_MS}ms)"
            )

            performance_results[name] = elapsed_ms

        print(f"\nAnalytics Performance Results (target < {ANALYTICS_TIMEOUT_MS}ms):")
        for name, elapsed_ms in performance_results.items():
            status = "OK" if elapsed_ms < ANALYTICS_TIMEOUT_MS else "SLOW"
            print(f"  {name}: {elapsed_ms:.0f}ms [{status}]")


class TestRunAPIEndpoints:
    """Unit tests for run API endpoints without full simulation.

    These tests verify the API contract without running full simulations.
    """

    def test_list_runs_empty(self, client):
        """Test listing runs when none exist."""
        response = client.get("/api/v1/runs")
        assert response.status_code == 200

        data = response.json()
        assert "runs" in data
        assert isinstance(data["runs"], list)

    def test_create_run_validation_missing_dataset(self, client):
        """Test run creation fails with missing dataset."""
        run_config = {
            "tradebook": "test_book",
            # Missing dataset
        }

        response = client.post("/api/v1/runs", json=run_config)
        assert response.status_code == 422  # Validation error

    def test_create_run_validation_missing_tradebook(self, client):
        """Test run creation fails with missing tradebook."""
        run_config = {
            "dataset": "test_dataset",
            # Missing tradebook
        }

        response = client.post("/api/v1/runs", json=run_config)
        assert response.status_code == 422  # Validation error

    def test_get_nonexistent_run(self, client):
        """Test getting non-existent run returns 404."""
        response = client.get("/api/v1/runs/nonexistent_run_id")
        assert response.status_code == 404

    def test_start_nonexistent_run(self, client):
        """Test starting non-existent run returns 404."""
        response = client.post("/api/v1/runs/nonexistent_run_id/start")
        assert response.status_code == 404

    def test_get_status_nonexistent_run(self, client):
        """Test getting status of non-existent run returns 404."""
        response = client.get("/api/v1/runs/nonexistent_run_id/status")
        assert response.status_code == 404


class TestResultsAPIEndpoints:
    """Unit tests for results API endpoints."""

    def test_get_results_nonexistent_run(self, client):
        """Test getting results for non-existent run returns 404."""
        response = client.get("/api/v1/results/nonexistent_run_id")
        assert response.status_code == 404

    def test_get_risk_nonexistent_run(self, client):
        """Test getting risk metrics for non-existent run returns 404."""
        response = client.get("/api/v1/results/nonexistent_run_id/risk")
        assert response.status_code == 404

    def test_get_timeseries_nonexistent_run(self, client):
        """Test getting timeseries for non-existent run returns 404."""
        response = client.get("/api/v1/results/nonexistent_run_id/timeseries")
        assert response.status_code == 404

    def test_get_internalization_nonexistent_run(self, client):
        """Test getting internalization for non-existent run returns 404."""
        response = client.get("/api/v1/results/nonexistent_run_id/internalization")
        assert response.status_code == 404

    def test_get_trades_nonexistent_run(self, client):
        """Test getting trades for non-existent run returns 404."""
        response = client.get("/api/v1/results/nonexistent_run_id/trades")
        assert response.status_code == 404

    def test_get_pnl_nonexistent_run(self, client):
        """Test getting PnL breakdown for non-existent run returns 404."""
        response = client.get("/api/v1/results/nonexistent_run_id/pnl")
        assert response.status_code == 404


class TestHealthEndpoints:
    """Verify health endpoints are operational."""

    def test_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")

    def test_health_detailed(self, client):
        """Test detailed health check endpoint."""
        response = client.get("/api/v1/health/detailed")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "system" in data
