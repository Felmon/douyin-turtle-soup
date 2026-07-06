import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.server import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers():
    from backend.server import ADMIN_TOKEN
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}
