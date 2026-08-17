from __future__ import annotations

from app.config import _cached_settings
from app.db import db_session, rebuild_database
from app.services import operational_messages as opmsg_service


def test_send_and_list_message(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    sent = opmsg_service.send_message(
        "SHP1001",
        "APT1001",
        "EMAIL",
        "agent@setuhaul.example",
        "carrier@example.com",
        "Test subject",
        "Test body",
    )
    assert sent["ok"] is True
    assert sent["delivery_status"] == "QUEUED"
    rows = opmsg_service.list_for_shipment("SHP1001")
    assert len(rows) == 1
    assert rows[0]["message_body"] == "Test body"


def test_reply_message(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPAND_SEED", "off")
    _cached_settings.cache_clear()
    rebuild_database(force=True)
    sent = opmsg_service.send_message(
        "SHP1001", None, "INTERNAL", "ops@example.com", "warehouse@example.com",
        "Original", "Original body",
    )
    reply = opmsg_service.reply_to_message(sent["operational_message_id"], "Reply body")
    assert reply["ok"] is True
    assert reply["reply_to_message_id"] == sent["operational_message_id"]
    rows = opmsg_service.list_for_shipment("SHP1001")
    assert len(rows) == 2
    assert rows[1]["message_body"] == "Reply body"
