#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────────────────────
# One-click deploy: Multi-Model LLM Router
# ────────────────────────────────────────────────────────────
# Prerequisites:
#   1. AWS CLI installed and configured
#   2. Node.js 20+ and npm installed
#   3. Python 3.12+ installed (for Lambda runtime)
#
# Usage:
#   ./scripts/deploy.sh                          # Deploy to us-east-1 (default)
#   AWS_GEOGRAPHY=eu ./scripts/deploy.sh         # Deploy to Europe geography
#   AWS_GEOGRAPHY=ap ./scripts/deploy.sh         # Deploy to Asia Pacific
#   TIER_SIMPLE_MODEL_ID=... ./scripts/deploy.sh # Override model IDs
# ────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "==> Checking prerequisites..."

command -v node >/dev/null 2>&1 || { echo "ERROR: node not found. Install Node.js 20+"; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "ERROR: npm not found."; exit 1; }
command -v aws  >/dev/null 2>&1 || { echo "ERROR: AWS CLI not found. Install awscli v2"; exit 1; }

# Verify AWS credentials
echo "==> Checking AWS credentials..."
aws sts get-caller-identity --output text 2>/dev/null || {
  echo "ERROR: AWS credentials not configured. Run 'aws configure' first."
  exit 1
}

# Geography config
GEOGRAPHY=${AWS_GEOGRAPHY:-"us"}
echo "==> Geography: ${GEOGRAPHY}"
echo "    (us = US regions, eu = Europe, ap = Asia Pacific)"
echo "    Set AWS_GEOGRAPHY=eu|ap to change, or override inference profiles directly."

# Install npm dependencies
echo "==> Installing dependencies..."
npm install

# Bootstrap CDK (idempotent — safe to run every time)
echo "==> Bootstrapping CDK (if needed)..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-$(aws configure get region || echo "us-east-1")}
npx cdk bootstrap "aws://${ACCOUNT_ID}/${REGION}"

# Deploy with geography context
echo "==> Deploying stack..."
AWS_GEOGRAPHY=${GEOGRAPHY} npx cdk deploy \
  --require-approval never \
  --context geography=${GEOGRAPHY}

echo ""
echo "✅ Deploy complete!"
ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name MultiModelRouter \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text 2>/dev/null || echo "<pending>")
echo "   API endpoint: ${ENDPOINT}"
echo "   Geography:    ${GEOGRAPHY}"
echo ""
echo "   Test it:"
echo "   curl -X POST ${ENDPOINT}/invoke \\"
echo '     -H "Content-Type: application/json" \\'
echo '     -d '\''{"prompt": "Summarize AI governance in 3 bullet points", "tier": "auto"}'\'
echo ""
