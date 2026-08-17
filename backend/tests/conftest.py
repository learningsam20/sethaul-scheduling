import os

import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("GEOAPIFY_API_KEY", "")
    monkeypatch.setenv("GEOAPIFY_HARD_FAIL", "false")
    from app.config import _cached_settings

    _cached_settings.cache_clear()
    from app.db import rebuild_database

    rebuild_database(force=True)
    yield
    _cached_settings.cache_clear()


@pytest.fixture
def crunch_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "crunch.db"))
    monkeypatch.setenv("EXPAND_SEED", "crunch")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("GEOAPIFY_API_KEY", "")
    from app.config import _cached_settings

    _cached_settings.cache_clear()
    from app.db import rebuild_database

    rebuild_database(force=True)
    yield
    _cached_settings.cache_clear()
