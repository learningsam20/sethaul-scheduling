from __future__ import annotations

import json

from app.config import _cached_settings
from app.db import db_session, rebuild_database
from app.services import metrics as metrics_service


def test_configurable_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    custom = {
        "human_help_rate": 0.8,
        "self_service_rate": 0.2,
        "avg_resolve_min": 30.0,
        "first_option_accept_rate": 0.5,
        "avg_eta_error_min": 20.0,
        "avg_wait_reduced_min": 5.0,
    }
    with db_session() as conn:
        conn.execute(
            "INSERT INTO app_settings(setting_key, setting_value, description, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value, updated_at=excluded.updated_at",
            ("manual_baseline", json.dumps(custom), "Manual baseline", "2026-01-01T00:00:00+05:30"),
        )
    with db_session() as conn:
        loaded = metrics_service.load_manual_baseline(conn)
    assert loaded["human_help_rate"] == 0.8
    assert loaded["avg_resolve_min"] == 30.0


def test_baseline_fallback_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    with db_session() as conn:
        loaded = metrics_service.load_manual_baseline(conn)
    assert loaded["human_help_rate"] == 1.0
    assert loaded["avg_resolve_min"] == 45.0
