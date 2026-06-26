#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────────────────────
# Test invocation of the deployed Multi-Model LLM Router
# ────────────────────────────────────────────────────────────
# Usage:
#   chmod +x scripts/invoke_test.sh
#   ./scripts/invoke_test.sh
#
# Requires:
#   - jq installed (brew install jq)
#   - Stack deployed and API_URL exported, or auto-detected
# ────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd")
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Auto-detect API URL from CloudFormation if not set
API_URL="${API_URL:-}"
if [ -z "$API_URL" ]; then
  echo "==> Auto-detecting API endpoint from CloudFormation..."
  API_URL=$(aws cloudformation describe-stacks \
    --stack-name MultiModelRouter \
    --query 'Stacks[0].Outputs[?OutputKey==`InvokeUrl`].OutputValue' \
    --output text 2>/dev/null || true)
fi

if [ -z "$API_URL" ] || [ "$API_URL" = "None" ]; then
  echo "ERROR: Could not determine API endpoint."
  echo "       Set API_URL manually or deploy the stack first."
  exit 1
fi

echo "API endpoint: $API_URL"

# ─── Test 1: Simple prompt → should route to Haiku ───
echo ""
echo "─── Test 1: Simple extraction ───"
curl -s -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Extract the date from this text: The meeting is on June 15, 2026."}' \
  | jq '{response: .response, tier: .routing.tier, profile: .routing.inference_profile, mode: .routing.mode, latency_ms: .routing.latency_ms}'

# ─── Test 2: Code prompt → should route to Sonnet 4 ───
echo ""
echo "─── Test 2: Code generation ───"
curl -s -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a Python function that implements a binary search tree with insert, delete, and search operations. Include time complexity analysis."}' \
  | jq '{response: .response, tier: .routing.tier, profile: .routing.inference_profile, latency_ms: .routing.latency_ms}'

# ─── Test 3: Analysis prompt → should route to Sonnet 3.5 ───
echo ""
echo "─── Test 3: Analysis ───"
curl -s -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Summarize the key differences between APRA CPS 230 and MAS TRM guidelines for operational resilience in financial services."}' \
  | jq '{response: .response, tier: .routing.tier, profile: .routing.inference_profile, latency_ms: .routing.latency_ms}'

# ─── Test 4: Health check ───
echo ""
echo "─── Test 4: Health check ───"
API_BASE="${API_URL%/invoke}"
curl -s "${API_BASE}/health" | jq '.'

echo ""
echo "✅ All tests completed."
