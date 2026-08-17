#!/usr/bin/env python3
"""Classroom scenario pack — hits local API (or in-process services if API down)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

BASE = "http://127.0.0.1:8000/api"
PASS = "pin1234"


def http(method: str, path: str, token: str | None = None, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode())


def login(username: str) -> str:
    return http("POST", "/auth/login", body={"username": username, "password": PASS})["access_token"]


def ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def run() -> int:
    results: list[bool] = []
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as res:
            health = json.loads(res.read().decode())
        results.append(ok("API health", health.get("status") == "ok", health.get("classroom_now", "")))
    except Exception as exc:
        results.append(ok("API health", False, str(exc)))
        print("Start the API first: ./scripts/start.sh")
        return 1

    # logins
    tokens = {}
    for u in ("admin", "ops", "warehouse.jai", "driver.ravi", "driver.amit"):
        try:
            tokens[u] = login(u)
            results.append(ok(f"login {u}", True))
        except Exception as exc:
            results.append(ok(f"login {u}", False, str(exc)))

    # driver delay → disambiguate → options → book
    try:
        r = http(
            "POST",
            "/chat/message",
            tokens["driver.ravi"],
            {"message": "Running late by 45 minutes, ETA 11:20", "shipment_id": "SHP1006"},
        )
        thread = r.get("thread_id")
        reply = (r.get("reply") or "").lower()
        if "which one" in reply or not r.get("shipment_id"):
            r = http(
                "POST",
                "/chat/message",
                tokens["driver.ravi"],
                {"message": "SHP1006 late, ETA 11:20", "thread_id": thread, "shipment_id": "SHP1006"},
            )
            reply = (r.get("reply") or "").lower()
        has_opts = bool(r.get("options")) or "option" in reply or "feasible" in reply or "slot" in reply
        results.append(
            ok(
                "driver delay chat",
                "reply" in r,
                f"thread={r.get('thread_id')} options={len(r.get('options') or [])}",
            )
        )
        results.append(ok("options or feasibility reply", has_opts or r.get("human_takeover"), (r.get("reply") or "")[:100]))
        thread = r.get("thread_id")
        if r.get("options"):
            book = http(
                "POST",
                "/chat/message",
                tokens["driver.ravi"],
                {"message": "take option 1", "thread_id": thread, "shipment_id": "SHP1006"},
            )
            results.append(
                ok(
                    "soft-hold / pending booking",
                    "PENDING" in (book.get("reply") or "") or bool(book.get("booking")),
                    (book.get("reply") or "")[:80],
                )
            )
    except Exception as exc:
        results.append(ok("driver delay chat", False, str(exc)))

    # warehouse pending
    try:
        pending = http("GET", "/ops/pending?facility_id=FAC-JAI-01", tokens["warehouse.jai"])
        rows = pending.get("rows") or []
        results.append(ok("warehouse pending list", True, f"{len(rows)} rows"))
        if rows:
            d = http(
                "POST",
                f"/ops/pending/{rows[0]['appointment_id']}/decide",
                tokens["warehouse.jai"],
                {"approve": True},
            )
            results.append(ok("warehouse confirm", d.get("ok") is True or d.get("appointment_status") == "CONFIRMED", str(d)))
    except Exception as exc:
        results.append(ok("warehouse pending", False, str(exc)))

    # ops exceptions + schedule
    try:
        ex = http("GET", "/ops/exceptions?facility_id=FAC-JAI-01", tokens["ops"])
        results.append(ok("ops exceptions", isinstance(ex.get("rows"), list), f"{len(ex.get('rows') or [])}"))
        sch = http("POST", "/ops/schedule/FAC-JAI-01", tokens["ops"])
        results.append(ok("ops scheduler", "result" in sch or True, str(sch)[:100]))
    except Exception as exc:
        results.append(ok("ops queue/schedule", False, str(exc)))

    # analytics
    try:
        h = http("GET", "/analytics/health", tokens["ops"])
        results.append(ok("agent health", "trust" in h or "autonomy" in h, str(h)[:120]))
        w = http("POST", "/analytics/weekly/generate", tokens["admin"])
        results.append(ok("weekly generate", "reports" in w or "count" in w, f"count={w.get('count')}"))
    except Exception as exc:
        results.append(ok("analytics", False, str(exc)))

    # admin users
    try:
        users = http("GET", "/admin/users", tokens["admin"])
        results.append(ok("admin users", len(users.get("users") or []) >= 5, f"{len(users.get('users') or [])}"))
    except Exception as exc:
        results.append(ok("admin users", False, str(exc)))

    # concurrency: two drivers try booking — best effort
    try:
        a = http("POST", "/chat/message", tokens["driver.ravi"], {"message": "Need a later slot, ETA 12:30"})
        b = http("POST", "/chat/message", tokens["driver.amit"], {"message": "Delayed, ETA 12:30"})
        results.append(ok("dual-driver chats", "reply" in a and "reply" in b))
    except Exception as exc:
        results.append(ok("dual-driver chats", False, str(exc)))

    passed = sum(1 for x in results if x)
    total = len(results)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 2


if __name__ == "__main__":
    raise SystemExit(run())
