"""Pytest fixtures for efxbt tests."""

import pytest
from fastapi.testclient import TestClient

from efxbt.app.main import app
from efxbt.core.cache import clear_all_caches


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear all caches before each test to ensure test isolation.

    This fixture runs automatically before every test.
    """
    clear_all_caches()
    yield
    # Also clear after test to ensure clean state
    clear_all_caches()
