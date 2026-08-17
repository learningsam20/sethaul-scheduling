from __future__ import annotations

from app.config import _cached_settings
from app.db import db_session, rebuild_database
from app.services import penalty


def test_penalty_create_and_decide(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    created = penalty.create_penalty_request(
        "SHP1001", "EXC001", "LATE_DELIVERY", 500.0, "Late by 45 min", "ops"
    )
    assert created["ok"] is True
    assert created["status"] == "PENDING"
    assert created["amount"] == 500.0
    decided = penalty.decide_penalty(created["penalty_request_id"], True, "admin")
    assert decided["ok"] is True
    assert decided["status"] == "APPROVED"
    rows = penalty.list_penalty_requests()
    assert any(r["penalty_request_id"] == created["penalty_request_id"] for r in rows)


def test_penalty_filter_by_status(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    p1 = penalty.create_penalty_request("SHP1001", None, "DAMAGE", 1000.0, "Dented crate", "ops")
    penalty.create_penalty_request("SHP1002", None, "LATE", 200.0, "Minor delay", "ops")
    penalty.decide_penalty(p1["penalty_request_id"], True, "admin")
    pending = penalty.list_penalty_requests(status="PENDING")
    approved = penalty.list_penalty_requests(status="APPROVED")
    assert len(pending) == 1
    assert len(approved) == 1
