#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STACK_NAME="${1:-SetuHaul-Stack}"
REGION="${AWS_REGION:-us-east-1}"

echo "=================================================="
echo "    SetuHaul AWS Deployment (Free Tier / EC2)    "
echo "=================================================="
echo "Region:     $REGION"
echo "Stack Name: $STACK_NAME"
echo ""

# Load environment variables from .env if present
if [[ -f .env ]]; then
  echo "Loading environment variables from .env..."
  set -a
  source .env
  set +a
fi

# Check AWS credentials
if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "⚠️  AWS credentials are not active or expired."
  echo "Please authenticate using: aws login"
  exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
echo "✅ Authenticated to AWS Account: $ACCOUNT_ID"

echo ""
echo "Step 1: Building frontend production bundle..."
./scripts/build.sh

echo ""
echo "Step 2: Ensuring AWS ECR Repository exists..."
aws ecr describe-repositories --repository-names setuhaul-app --region "$REGION" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name setuhaul-app --region "$REGION" >/dev/null

ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/setuhaul-app:latest"

echo ""
echo "Step 3: Authenticating Docker with AWS ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

echo ""
echo "Step 4: Building production Linux container (x86_64)..."
docker build --platform linux/amd64 -t "$ECR_URI" .

echo ""
echo "Step 5: Pushing container image to AWS ECR..."
docker push "$ECR_URI"

echo ""
echo "Step 6: Registering AWS CloudWatch Dashboard..."
aws cloudwatch put-dashboard \
  --dashboard-name "SetuHaul-Operations" \
  --dashboard-body "file://deploy/cloudwatch-dashboard.json" \
  --region "$REGION" >/dev/null
echo "✅ CloudWatch Dashboard 'SetuHaul-Operations' registered."

echo ""
echo "Step 7: Deploying AWS CloudFormation Stack ($STACK_NAME)..."
OPENROUTER_KEY="${OPENROUTER_API_KEY:-}"
OPENROUTER_BASE="${OPENROUTER_BASE_URL:-https://bedrock-mantle.us-east-1.api.aws/v1}"
OPENROUTER_MOD="${OPENROUTER_MODEL:-zai.glm-4.7-flash}"
GEOAPIFY_KEY="${GEOAPIFY_API_KEY:-}"
LANGSMITH_KEY="${LANGSMITH_API_KEY:-}"
LANGSMITH_TRACING="${LANGCHAIN_TRACING_V2:-true}"
LANGSMITH_PROJ="${LANGSMITH_PROJECT:-SETUHAUL}"
JWT_SEC="${JWT_SECRET:-setuhaul-dev-secret-change-me}"

aws cloudformation deploy \
  --template-file deploy/aws-ec2-stack.yaml \
  --stack-name "$STACK_NAME" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    ImageUri="$ECR_URI" \
    OpenRouterApiKey="$OPENROUTER_KEY" \
    OpenRouterBaseUrl="$OPENROUTER_BASE" \
    OpenRouterModel="$OPENROUTER_MOD" \
    GeoapifyApiKey="$GEOAPIFY_KEY" \
    LangsmithApiKey="$LANGSMITH_KEY" \
    LangchainTracingV2="$LANGSMITH_TRACING" \
    LangsmithProject="$LANGSMITH_PROJ" \
    JwtSecret="$JWT_SEC" \
  --region "$REGION"

echo ""
echo "Step 8: Retrieving Stack Outputs..."
APP_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='AppURL'].OutputValue" \
  --output text \
  --region "$REGION" || true)

DASHBOARD_URL="https://${REGION}.console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards:name=SetuHaul-Operations"

echo ""
echo "=================================================="
echo "🎉 SETUHAUL DEPLOYMENT SUCCESSFUL!"
echo "=================================================="
echo "🌐 Live App URL:          $APP_URL"
echo "📊 CloudWatch Dashboard:  $DASHBOARD_URL"
echo "=================================================="
