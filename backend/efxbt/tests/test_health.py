"""Tests for health check endpoints."""

from fastapi.testclient import TestClient

from efxbt.core.config import Defaults


class TestHealthEndpoint:
    """Tests for the /api/v1/health endpoint."""

    def test_health_returns_200(self, client: TestClient) -> None:
        """Health endpoint returns 200 OK."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_returns_required_fields(self, client: TestClient) -> None:
        """Health response contains all required fields."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert "status" in data
        assert "timestamp_ms" in data
        assert "version" in data
        assert "checks" in data

    def test_health_status_is_healthy(self, client: TestClient) -> None:
        """Health status is 'healthy' when all checks pass."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert data["status"] == "healthy"

    def test_health_version_matches(self, client: TestClient) -> None:
        """Health response version matches Defaults.VERSION."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert data["version"] == Defaults.VERSION

    def test_health_timestamp_is_positive(self, client: TestClient) -> None:
        """Health timestamp is a positive integer."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert isinstance(data["timestamp_ms"], int)
        assert data["timestamp_ms"] > 0

    def test_health_duckdb_check_passes(self, client: TestClient) -> None:
        """DuckDB health check passes."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert "duckdb" in data["checks"]
        assert data["checks"]["duckdb"] is True


class TestDetailedHealthEndpoint:
    """Tests for the /api/v1/health/detailed endpoint."""

    def test_detailed_health_returns_200(self, client: TestClient) -> None:
        """Detailed health endpoint returns 200 OK."""
        response = client.get("/api/v1/health/detailed")
        assert response.status_code == 200

    def test_detailed_health_includes_system_info(self, client: TestClient) -> None:
        """Detailed health response includes system information."""
        response = client.get("/api/v1/health/detailed")
        data = response.json()

        assert "system" in data
        assert "cpu_percent" in data["system"]
        assert "memory_percent" in data["system"]
        assert "memory_available_mb" in data["system"]
        assert "duckdb_version" in data["system"]

    def test_detailed_health_system_values_are_valid(self, client: TestClient) -> None:
        """System values are within expected ranges."""
        response = client.get("/api/v1/health/detailed")
        data = response.json()

        # CPU percent should be 0-100 (or slightly higher on multi-core systems)
        assert 0 <= data["system"]["cpu_percent"] <= 1000

        # Memory percent should be 0-100
        assert 0 <= data["system"]["memory_percent"] <= 100

        # Available memory should be positive
        assert data["system"]["memory_available_mb"] > 0


class TestStubEndpoints:
    """Tests for stub endpoints that should return 501."""

    def test_datasets_is_implemented(self, client: TestClient) -> None:
        """Datasets endpoint is now implemented and returns 200."""
        response = client.get("/api/v1/datasets")
        # Should return 200 with empty list (no datasets in test)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_runs_is_implemented(self, client: TestClient) -> None:
        """Runs endpoint is now implemented and returns 200."""
        response = client.get("/api/v1/runs")
        # Should return 200 with empty list (no runs in test)
        assert response.status_code == 200
        data = response.json()
        assert "runs" in data
        assert isinstance(data["runs"], list)

    def test_sweeps_is_implemented(self, client: TestClient) -> None:
        """Sweeps endpoint is now implemented and returns 200."""
        response = client.get("/api/v1/sweeps")
        # Should return 200 with empty list (no sweeps in test)
        assert response.status_code == 200
        data = response.json()
        assert "sweeps" in data
        assert isinstance(data["sweeps"], list)
