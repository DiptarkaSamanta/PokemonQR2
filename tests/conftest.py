from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(data_dir_override=tmp_path)
    with TestClient(app) as tc:
        yield tc
