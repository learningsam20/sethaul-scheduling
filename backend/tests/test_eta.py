from app.db import db_session
from app.services import eta, chat, metrics as metrics_service


def test_stale_location_rejected(db):
    chat.create_thread("DRV006", "SHP1006")
    loc = eta.save_location_snapshot(
        "THR001",
        "DRV006",
        "SHP1006",
        26.9,
        75.8,
        12.0,
        "2026-08-04T09:00:00+05:30",
    )
    result = eta.compute_route_eta(
        "SHP1006",
        "THR001",
        loc["location_id"],
        client_now="2026-08-04T09:10:00+05:30",
    )
    assert result["ok"] is False
    assert result["error"] == "stale_location"
    assert result["stale"] is True


def test_already_at_gate(db):
    loc = eta.save_location_snapshot(
        "THR007",
        "DRV003",
        "SHP1003",
        26.91,
        75.78,
        8.0,
        "2026-08-04T09:40:00+05:30",
    )
    result = eta.compute_route_eta(
        "SHP1003",
        "THR007",
        loc["location_id"],
        client_now="2026-08-04T09:40:05+05:30",
    )
    assert result["ok"] is True
    assert result.get("at_gate") is True
    assert result["provider"] == "AT_GATE"


def test_hard_outage(db, monkeypatch):
    monkeypatch.setenv("GEOAPIFY_HARD_FAIL", "true")
    monkeypatch.setenv("GEOAPIFY_API_KEY", "")
    from app.config import _cached_settings

    _cached_settings.cache_clear()
    loc = eta.save_location_snapshot(
        "THR001",
        "DRV006",
        "SHP1006",
        26.85,
        75.70,
        10.0,
        "2026-08-04T09:40:00+05:30",
    )
    result = eta.compute_route_eta(
        "SHP1006",
        "THR001",
        loc["location_id"],
        client_now="2026-08-04T09:40:02+05:30",
    )
    assert result["ok"] is False
    assert result.get("hard_outage") is True or result.get("error") == "routing_unavailable"


def test_delay_vs_eta_mismatch_noted(db):
    result = eta.record_driver_eta(
        "SHP1006",
        "DRV006",
        "2026-08-04T18:00:00+05:30",
        delay_min=45,
        thread_id="THR001",
    )
    assert result.get("delay_eta_mismatch")


def test_cloudwatch_push_falls_back_to_scrape(db):
    from app.services import metrics as metrics_service

    result = metrics_service.push_cloudwatch_metrics()
    assert "scrape_path" in result
    assert result.get("pushed") in (True, False)
    if not result.get("pushed"):
        assert result.get("reason") in ("boto3_not_installed", "no_metric_samples") or "payload" in result


def test_wait_projection_recorded(db):
    from app.services import metrics as metrics_service

    metrics_service.ensure_case_metric("THR001", "SHP1006", "DRV006", "FAC-JAI-01", "CAR003")
    ranked = eta.rank_slots_with_eta_buffers("SHP1006", declared_eta_ts="2026-08-04T11:20:00+05:30")
    metrics_service.record_wait_projection(
        "THR001",
        ranked.get("projected_wait_old_min"),
        ranked.get("projected_wait_new_min"),
        predicted_eta_ts="2026-08-04T11:20:00+05:30",
        eta_source="DRIVER_DECLARED",
    )
    metrics_service.record_options_generated("THR001", ranked.get("options") or [])
    with db_session() as conn:
        row = conn.execute("SELECT * FROM case_metrics WHERE thread_id='THR001'").fetchone()
    assert row["projected_wait_old_min"] is not None or ranked.get("projected_wait_old_min") is None
    assert row["options_generated_at"]
    assert row["eta_source_used"] == "DRIVER_DECLARED"
