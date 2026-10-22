import pytest

from app.config import load_settings
from app.rag import Assistant


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("LLM_PROVIDER", "extractif")


@pytest.fixture
def assistant():
    return Assistant(load_settings())
