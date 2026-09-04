import os

os.environ["DATABASE_PATH"] = "/tmp/mpesa_gateway_test.db"
os.environ["SIMULATION_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import database
    monkeypatch.setattr(database.settings, "database_path", str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client
