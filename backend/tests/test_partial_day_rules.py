from __future__ import annotations

from app.config import _cached_settings
from app.db import db_session, get_setting, rebuild_database
from app.services import booking


def test_partial_day_rule_applies_within_window(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    with db_session() as conn:
        conn.execute(
            "UPDATE app_settings SET setting_value = ? WHERE setting_key = 'classroom_now'",
            ("2026-08-04T14:30:00+05:30",),
        )
        rules = booking._facility_rules(conn, "FAC-JAI-01")
    assert "PARTIAL_DAY_WINDOW" in rules


def test_partial_day_rule_excluded_outside_window(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    with db_session() as conn:
        conn.execute(
            "UPDATE app_settings SET setting_value = ? WHERE setting_key = 'classroom_now'",
            ("2026-08-04T10:30:00+05:30",),
        )
        rules = booking._facility_rules(conn, "FAC-JAI-01")
    assert "PARTIAL_DAY_WINDOW" not in rules


def test_partial_day_rule_included_at_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    with db_session() as conn:
        conn.execute(
            "UPDATE app_settings SET setting_value = ? WHERE setting_key = 'classroom_now'",
            ("2026-08-04T14:00:00+05:30",),
        )
        rules = booking._facility_rules(conn, "FAC-JAI-01")
    assert "PARTIAL_DAY_WINDOW" in rules
