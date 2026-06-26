#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────────────────────
# Initial project setup for local development
# ────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "==> Installing npm dependencies..."
npm install

echo "==> Installing Python test dependencies..."
pip3 install -q boto3 botocore pytest 2>/dev/null || true

echo ""
echo "✅ Setup complete. Next steps:"
echo "   1. Configure AWS credentials:  aws configure"
echo "   2. Deploy:                      npm run deploy"
echo "   3. Test:                        bash scripts/invoke_test.sh"
echo ""
