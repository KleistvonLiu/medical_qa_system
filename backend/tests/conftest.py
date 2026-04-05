from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.database import engine, init_db
from app.main import app


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    path = FIXTURES_DIR / name
    if path.suffix == ".json":
        return json.loads(path.read_text())
    return path.read_text()


@pytest.fixture(autouse=True)
def reset_database():
    SQLModel.metadata.drop_all(engine)
    init_db()
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

