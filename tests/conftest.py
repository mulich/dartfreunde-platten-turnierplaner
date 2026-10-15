"""Allow testing this independent application from the parent repository."""
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_portal_requests(monkeypatch):
    monkeypatch.setenv('DARTPORTAL_URL', '')
