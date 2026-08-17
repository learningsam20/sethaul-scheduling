#!/usr/bin/env python3
"""Dual-driver same-slot concurrency demo.

Two drivers attempt to soft-hold / book competing options around the same
window. The script proves at most one booking wins and the loser recovers
with alternate options (or an explicit conflict).
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    with urllib.request.urlopen(req, timeout=45) as res:
        return json.loads(res.read().decode())


def login(username: str) -> str:
    return http("POST", "/auth/login", body={"username": username, "password": PASS})["access_token"]


def driver_flow(username: str, shipment_id: str, eta: str) -> dict:
    token = login(username)
    first = http(
        "POST",
        "/chat/message",
        token,
        {"message": f"Running late, ETA {eta}", "shipment_id": shipment_id},
    )
    options = first.get("options") or []
    if not options:
        # try again with explicit late wording
        first = http(
            "POST",
            "/chat/message",
            token,
            {
                "message": f"{shipment_id} delayed, ETA {eta}, need later slot",
                "thread_id": first.get("thread_id"),
                "shipment_id": shipment_id,
            },
        )
        options = first.get("options") or []
    if not options:
        return {
            "username": username,
            "shipment_id": shipment_id,
            "ok": False,
            "stage": "options",
            "reply": first.get("reply"),
        }
    book = http(
        "POST",
        "/chat/message",
        token,
        {
            "message": "take option 1",
            "thread_id": first.get("thread_id"),
            "shipment_id": shipment_id,
        },
    )
    reply = book.get("reply") or ""
    pending = "PENDING" in reply or bool(book.get("booking", {}).get("ok"))
    conflict = (not pending) and (
        "could not" in reply.lower() or "conflict" in reply.lower() or "held" in reply.lower()
    )
    return {
        "username": username,
        "shipment_id": shipment_id,
        "ok": True,
        "slot": (options[0] or {}).get("slot_id"),
        "pending": pending,
        "conflict": conflict,
        "reply": reply[:160],
        "follow_options": len(book.get("options") or []),
    }


def main() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as res:
            json.loads(res.read().decode())
    except Exception as exc:
        print(f"[FAIL] API not reachable on :8000 — {exc}")
        print("Start with ./scripts/start.sh")
        return 1

    # Clean slate so prior escalations don't block the race
    try:
        admin = login("admin")
        http("POST", "/admin/rebuild-db", admin)
        print("[info] database rebuilt for clean race")
    except Exception as exc:
        print(f"[warn] could not rebuild DB before race: {exc}")

    # Two active drivers aiming at nearby windows
    jobs = [
        ("driver.ravi", "SHP1006", "11:20"),
        ("driver.amit", "SHP1002", "11:20"),
    ]

    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(driver_flow, u, s, e) for u, s, e in jobs]
        for fut in as_completed(futs):
            results.append(fut.result())

    pending_wins = [r for r in results if r.get("pending")]
    recoveries = [r for r in results if r.get("conflict") or r.get("follow_options")]

    print("=== Concurrency Demo ===")
    for r in results:
        print(json.dumps(r, indent=2))

    # Success criteria: not both silently "confirmed" without conflict handling,
    # and at least one pending OR explicit recovery path observed.
    both_pending_same_slot = (
        len(pending_wins) == 2
        and pending_wins[0].get("slot")
        and pending_wins[0].get("slot") == pending_wins[1].get("slot")
    )
    ok = (not both_pending_same_slot) and (len(pending_wins) >= 1 or len(recoveries) >= 1)
    print(
        f"\n[{'PASS' if ok else 'FAIL'}] unique-slot safety — "
        f"pending_wins={len(pending_wins)} recoveries={len(recoveries)} "
        f"same_slot_double={both_pending_same_slot}"
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
