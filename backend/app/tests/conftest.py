"""Shared pytest fixtures: isolated temp SQLite DB per session + API client."""

import os
import tempfile

import pytest

_tmpdir = tempfile.mkdtemp(prefix="agenticwhats-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db".replace("\\", "/")
os.environ["JWT_SECRET"] = "test-secret-for-pytest-only"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.entities import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def db():
    return SessionLocal()


@pytest.fixture(scope="session")
def tenant(client):
    """Register a business and return {token, business_id, headers}."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    r = client.post("/api/auth/register", json={
        "name": "Test Owner", "email": f"owner-{suffix}@test.com", "password": "password123",
        "business_name": f"Test Restaurant {suffix}",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    return {
        "token": data["access_token"],
        "business_id": data["business_id"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "email": f"owner-{suffix}@test.com",
        "password": "password123",
    }
