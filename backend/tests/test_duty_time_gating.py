from __future__ import annotations

from app.config import _cached_settings
from app.db import db_session, rebuild_database
from app.services import duty


def test_duty_decrement_on_slot(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    result = duty.update_duty_after_slot("DRV001", "2026-08-04T10:00:00+05:30", unload_min=60, buffer_min=15)
    assert result["ok"] is True
    assert result["deducted_min"] == 75
    assert result["new_remaining"] == 525


def test_duty_cannot_accept_short_remaining(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    with db_session() as conn:
        conn.execute("UPDATE drivers SET remaining_duty_minutes = 30 WHERE driver_id = 'DRV001'")
    check = duty.can_accept_slot("DRV001", "2026-08-04T10:00:00+05:30", expected_unload_min=60)
    assert check["ok"] is True
    assert check["can_accept"] is False
    assert check["reason"] == "insufficient_duty_time"


def test_duty_reimburse_on_cancel(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    with db_session() as conn:
        conn.execute("UPDATE drivers SET remaining_duty_minutes = 30 WHERE driver_id = 'DRV001'")
    result = duty.reimburse_duty("DRV001", 30)
    assert result["ok"] is True
    assert result["new_remaining"] == 60
