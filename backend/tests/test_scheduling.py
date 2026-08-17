from app.services import scheduling, booking


def test_scheduler_assigns_intervals(db):
    result = scheduling.run_facility_schedule("FAC-JAI-01", trigger="test")
    assert result["assignments"]
    assert any(a.get("fixed") for a in result["assignments"]) or result["kpis"]["assigned"] >= 1
    assert "slot_utilisation_pct" in result["kpis"]
    assert "priority_violations" in result["kpis"]
    for a in result["assignments"]:
        assert a["assigned_start_ts"] < a["assigned_end_ts"]
        assert a.get("dock_code")


def test_replan_on_cancel(db):
    before = scheduling.run_facility_schedule("FAC-JAI-01", trigger="before")
    booking.cancel_appointment("APT1013A", "replan test", "ops")
    after = scheduling.run_facility_schedule("FAC-JAI-01", trigger="after_cancel")
    assert after["run_id"] != before["run_id"]
    assert after["kpis"]["assigned"] >= 1
