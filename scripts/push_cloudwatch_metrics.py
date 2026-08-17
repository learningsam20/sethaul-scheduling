#!/usr/bin/env python3
"""Push SetuHaul agent KPIs to CloudWatch, or print the scrape payload if AWS is unavailable.

Scrape path (no AWS required): GET /api/analytics/cloudwatch-metrics
Live push: POST /api/analytics/cloudwatch-metrics/push  (needs boto3 + AWS creds)
Dashboard: deploy/cloudwatch-dashboard.json
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import metrics as metrics_service  # noqa: E402


def main() -> int:
    facility = os.environ.get("SETUHAUL_FACILITY_ID") or None
    result = metrics_service.push_cloudwatch_metrics(facility)
    print(json.dumps({k: v for k, v in result.items() if k != "payload"}, indent=2, default=str))
    if not result.get("pushed"):
        print("\nScrape instead:", result.get("scrape_path", "GET /api/analytics/cloudwatch-metrics"))
        if result.get("payload"):
            print(json.dumps(result["payload"], indent=2, default=str)[:2000])
        return 0 if result.get("reason") in ("boto3_not_installed", "no_metric_samples") else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
