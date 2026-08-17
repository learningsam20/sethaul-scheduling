#!/usr/bin/env bash
# T1a helper: build artifacts for S3+CloudFront UI + container/Lambda API.
# Does not create AWS resources automatically — prints the intended deploy steps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

./scripts/build.sh

BUCKET="${SETUHAUL_UI_BUCKET:-}"
REGION="${AWS_REGION:-ap-south-1}"

echo "=== SetuHaul deploy plan (T1a) ==="
echo "1) UI: sync frontend/dist to S3 + invalidate CloudFront"
if [[ -n "$BUCKET" ]]; then
  aws s3 sync frontend/dist "s3://${BUCKET}/" --delete --region "$REGION"
  echo "Synced to s3://${BUCKET}/"
else
  echo "   Skip sync (set SETUHAUL_UI_BUCKET to enable)"
fi
echo "2) API: push container image and update Lambda Function URL / Lightsail service"
echo "   docker build -t setuhaul-api -f Dockerfile ."
echo "   # then push to ECR and update Lambda/Lightsail with env from .env"
echo "3) Confirm SQLite path / seed reset strategy for the chosen host"
echo "4) Metrics: scrape GET /api/analytics/cloudwatch-metrics"
echo "   Live push: python3 scripts/push_cloudwatch_metrics.py  (needs boto3 + AWS creds)"
echo "   Dashboard template: deploy/cloudwatch-dashboard.json"
echo "   aws cloudwatch put-dashboard --dashboard-name SetuHaul --dashboard-body file://deploy/cloudwatch-dashboard.json"
echo "Done."
