"""Pytest fixtures for efxbt tests."""

import pytest
from fastapi.testclient import TestClient

from efxbt.app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)
