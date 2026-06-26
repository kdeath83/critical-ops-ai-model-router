# 🧠 AWS Multi-Model LLM Router

Route prompts to the right frontier model based on complexity — using **native AWS services** and **cross-region inference profiles**.

```
User Prompt ──▶ API Gateway ──▶ Lambda Router ──▶ Provider Dispatch
                                    │                    │
                              ┌─────┴──────┐    ┌───────┴────────┐
                              │ Classifier  │    │  Bedrock       │
                              │ (heuristic) │    │  OpenAI-compat │
                              └─────┬──────┘    │  Kimi / etc.   │
                                    │            └───────┬────────┘
                    ┌───────────────┼───────────────┐     │
                    ▼               ▼               ▼     │
              ┌──────────┐  ┌────────────┐  ┌──────────────┐ │
              │  Simple  │  │  Medium    │  │    Hard      │ │
              │  Haiku   │  │ Sonnet 3.5 │  │  Sonnet 4    │ │
              │  — or —  │  │  — or —    │  │  — or —      │ │
              │  Kimi    │  │  GPT-4o    │  │  GPT-4o      │ │
              └────┬─────┘  └─────┬──────┘  └──────┬───────┘ │
                   │              │                 │        │
                   └──────────────┼─────────────────┘────────┘
                                  ▼
                    ┌──────────────────────────┐
                    │ Cross-Region Inference   │
                    │ (Bedrock) or direct API  │
                    └──────────────────────────┘
```

## 🎯 What It Does

| Tier | Model | Inference Profile | Use Case | ~Cost/1K req |
|------|-------|------------------|----------|-------------|
| **Simple** | Claude 3.5 Haiku | `{geography}.anthropic.claude-3-5-haiku-...` | Extraction, formatting, Q&A | ~$0.80 |
| **Medium** | Claude Sonnet 4 | `{geography}.anthropic.claude-sonnet-4-...` | Summarization, analysis, RAG | ~$15.00 |
| **Complex** | Claude Opus 4.8 | `{geography}.anthropic.claude-opus-4-8-...` | Code gen, multi-step reasoning | ~$60.00 |

The **classifier uses heuristics** (no LLM call for routing):
- Token length estimation
- Code block detection
- Reasoning complexity markers
- Structured output requirements
- Multi-step instruction detection

### Region Configuration

Choose which AWS regions to use for cross-region inference by setting the **geography**. System-defined inference profiles route automatically across all regions in the selected geography.

| Geography | Regions | Inference profile pattern |
|-----------|---------|--------------------------|
| `us` (default) | `us-east-1`, `us-east-2`, `us-west-2` | `us.anthropic.claude-*` |
| `eu` | `eu-west-1`, `eu-west-2`, `eu-west-3`, `eu-central-1`, `eu-north-1` | `eu.anthropic.claude-*` |
| `ap` | `ap-northeast-1/2/3`, `ap-southeast-1/2/3`, `ap-south-1` | `ap.anthropic.claude-*` |

**Set geography at deploy time:**

```bash
# Default: US regions
bash scripts/deploy.sh

# Europe geography
AWS_GEOGRAPHY=eu bash scripts/deploy.sh

# Asia Pacific
AWS_GEOGRAPHY=ap bash scripts/deploy.sh
```

Or via CDK context:
```bash
npx cdk deploy --context geography=eu
```

Geography is auto-detected from the deployment region if not set:
- `us-east-1` / `us-east-2` / `us-west-2` → `us`
- Any `eu-*` region → `eu`
- Any `ap-*` region → `ap`

**Need a different region mix?** Override individual inference profiles via environment variables for full control:
```bash
TIER_SIMPLE_INFERENCE_PROFILE=us.anthropic.claude-3-haiku-20240307-v1:0 \
TIER_MEDIUM_INFERENCE_PROFILE=us.anthropic.claude-3-5-sonnet-20241022-v2:0 \
TIER_HARD_INFERENCE_PROFILE=us.anthropic.claude-sonnet-4-20250514-v1:0 \
npx cdk deploy
```

This allows deploying in `eu-west-1` while using US inference profiles, or creating custom `APPLICATION`-type inference profiles across any region set.

### Cross-Region Benefits

Each tier uses a **system-defined cross-region inference profile** that provides:
- **Higher throughput** — distributes load across regions
- **Automatic failover** — if one region is saturated, requests route to another
- **No extra cost** — cross-region inference is free
- **Lower latency** — requests route to the optimal region in your geography

## 🚀 One-Click Deploy

### Option 1: Deploy from your machine

```bash
git clone <your-repo>
cd aws-multi-model-router

# Configure AWS credentials (if not done)
aws configure

# One command to deploy
npm install && npx cdk bootstrap && npx cdk deploy --require-approval never
```

Or use the deploy script:

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

### Option 2: GitHub Actions (CI/CD)

1. Fork/clone this repo to GitHub
2. Add these **secrets** to your repo:
   - `AWS_ACCOUNT_ID` — your AWS account ID
   - `AWS_DEPLOY_ROLE_ARN` — IAM role ARN for GitHub OIDC
3. Push to `main` — deploys automatically

> **Set up OIDC**: Follow the [AWS guide](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services) to create a role with `cdk:*` and `bedrock:InvokeModel` permissions.

### Prerequisites

- AWS CLI v2 (`brew install awscli`)
- Node.js 20+
- Python 3.12+ (for Lambda runtime)
- Bedrock model access enabled in your AWS account

## 🖥️ Frontend Dashboard

The deploy includes a **live flow visualization dashboard** hosted on CloudFront.

```
Deploy output includes:
  FrontendUrl = https://dxxxxx.cloudfront.net
```

### Features

- **Animated pipeline** — watch requests flow User → API GW → Classifier → Router → Provider → Response
- **Live mode** — connect to your deployed API endpoint to see real traffic
- **Demo mode** — click "Simulate" to see the flow with sample prompts across all tiers/providers
- **Stats cards** — request counts per tier with percentages
- **30s rolling chart** — request volume over time
- **Provider donut** — Bedrock vs OpenAI vs Kimi split
- **Request log** — full history with tier badges, latency, token counts
- **Click any log row** — opens detail modal with full routing metadata (inference profile, mode, region, classification reason, response text)

### Manual access

Open `frontend/index.html` directly in your browser for demo mode (no deploy needed).

### Connecting to live API

1. Open the dashboard (CloudFront URL or local file)
2. Click **🔌 Live** button in the header
3. Enter your API endpoint URL (from deploy output: `InvokeUrl`)
4. Type a prompt and hit Send — requests flow through your deployed router

## 📡 API

### `POST /invoke`

```bash
curl -X POST https://<api-endpoint>/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain the difference between REST and GraphQL",
    "system_prompt": "You are a technical educator",
    "tier": "auto",
    "temperature": 0.3,
    "max_tokens": 1024
  }'
```

**Parameters:**

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `prompt` | ✅ | — | The user prompt |
| `system_prompt` | ❌ | `""` | System context |
| `tier` | ❌ | `"auto"` | `"auto"`, `"simple"`, `"medium"`, or `"hard"` |
| `temperature` | ❌ | tier default | 0.0–1.0 |
| `max_tokens` | ❌ | tier default | Max output tokens |
| `force_direct` | ❌ | `false` | Skip cross-region profile, use direct model ID |

**Response:**

```json
{
  "success": true,
  "response": "REST and GraphQL differ in...",
  "routing": {
    "tier": "medium",
    "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "inference_profile": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "mode": "profile",
    "latency_ms": 1234,
    "region": "us-east-1"
  },
  "usage": {
    "input_tokens": 45,
    "output_tokens": 120,
    "total_tokens": 165
  },
  "classification": {
    "tier": "medium",
    "reason": "analysis/reasoning requested (1 markers)",
    "token_estimate": 12
  }
}
```

### `GET /health`

```json
{
  "status": "healthy",
  "tiers": ["simple", "medium", "hard"],
  "region": "us-east-1"
}
```

## 💻 Local Development

```bash
# Setup
bash scripts/configure.sh

# Run tests
cd aws-multi-model-router
python3 -m pytest test/ -v
```

## 🔧 Configuration

### Geography

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_GEOGRAPHY` | auto-detected from region | `"us"`, `"eu"`, or `"ap"` |

### Multi-Provider (per tier)

Each tier is independently configurable. Mix and match providers across tiers.

| Variable | Default | Description |
|----------|---------|-------------|
| `TIER_{TIER}_PROVIDER` | `bedrock` | `"bedrock"` or `"openai"` (OpenAI, Kimi, etc.) |
| `TIER_{TIER}_MODEL_ID` | *(tier default)* | Model name/ID |
| `TIER_{TIER}_INFERENCE_PROFILE` | auto (geography-based) | Bedrock cross-region profile |
| `TIER_{TIER}_API_BASE` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `TIER_{TIER}_API_KEY` | — | API key for OpenAI-compatible providers |

Where `{TIER}` is `SIMPLE`, `MEDIUM`, or `HARD`.

#### Defaults

| Variable | Default |
|----------|---------|
| `TIER_SIMPLE_PROVIDER` | `bedrock` |
| `TIER_SIMPLE_MODEL_ID` | `anthropic.claude-3-5-haiku-20241022-v1:0` |
| `TIER_SIMPLE_INFERENCE_PROFILE` | `{geography}.anthropic.claude-3-5-haiku-20241022-v1:0` |
| `TIER_MEDIUM_PROVIDER` | `bedrock` |
| `TIER_MEDIUM_MODEL_ID` | `anthropic.claude-sonnet-4-20250514-v1:0` |
| `TIER_MEDIUM_INFERENCE_PROFILE` | `{geography}.anthropic.claude-sonnet-4-20250514-v1:0` |
| `TIER_HARD_PROVIDER` | `bedrock` |
| `TIER_HARD_MODEL_ID` | `anthropic.claude-opus-4-8` |
| `TIER_HARD_INFERENCE_PROFILE` | `{geography}.anthropic.claude-opus-4-8` |

#### Examples

**Simple → Kimi, Medium → Bedrock, Hard → OpenAI:**

```bash
# Kimi for simple tasks
TIER_SIMPLE_PROVIDER=openai \
TIER_SIMPLE_MODEL_ID=moonshot-v1-8k \
TIER_SIMPLE_API_BASE=https://api.moonshot.cn/v1 \
TIER_SIMPLE_API_KEY=sk-... \
# OpenAI for hard reasoning
TIER_HARD_PROVIDER=openai \
TIER_HARD_MODEL_ID=gpt-4o \
TIER_HARD_API_KEY=sk-... \
# Medium stays on Bedrock (default)
npx cdk deploy
```

**All three tiers on different providers:**

```bash
TIER_SIMPLE_PROVIDER=bedrock \
TIER_MEDIUM_PROVIDER=openai \
TIER_MEDIUM_MODEL_ID=gpt-4o-mini \
TIER_MEDIUM_API_KEY=sk-... \
TIER_HARD_PROVIDER=openai \
TIER_HARD_MODEL_ID=moonshot-v1-128k \
TIER_HARD_API_BASE=https://api.moonshot.cn/v1 \
TIER_HARD_API_KEY=sk-... \
npx cdk deploy
```

**All-Bedrock with custom models (Llama 3, Mistral):**

```bash
export TIER_SIMPLE_MODEL_ID=meta.llama3-8b-instruct-v1:0
export AWS_GEOGRAPHY=us
npx cdk deploy --context geography=us
```

**Europe deployment with explicit profiles:**

```bash
export AWS_GEOGRAPHY=eu
export TIER_SIMPLE_INFERENCE_PROFILE=eu.anthropic.claude-3-haiku-20240307-v1:0
npx cdk deploy --context geography=eu
```

> **🔐 API keys:** For production, store keys in AWS Secrets Manager and reference them in the Lambda environment. The env-var approach is fine for dev/demo.

### Load Balancing (per tier, multi-target)

Each tier can have **multiple targets** with weighted load balancing. The router picks a target at random proportional to its weight.

**Configure via JSON env var:**

```bash
# Simple: 80% Bedrock Haiku, 20% GPT-4o-mini
TIER_SIMPLE_CONFIG='[
  {"provider":"bedrock","model_id":"anthropic.claude-3-haiku-20240307-v1:0","weight":80},
  {"provider":"openai","model_id":"gpt-4o-mini","weight":20}
]' npx cdk deploy
```

**Default:** Single target (Bedrock, weight 100) — backward compatible.

**All three tiers with custom load balancing:**

```bash
TIER_SIMPLE_CONFIG='[{"provider":"bedrock","model_id":"anthropic.claude-3-haiku-20240307-v1:0","weight":80},{"provider":"openai","model_id":"gpt-4o-mini","weight":20}]' \
TIER_MEDIUM_CONFIG='[{"provider":"bedrock","model_id":"anthropic.claude-3-5-sonnet-20241022-v2:0","weight":70},{"provider":"openai","model_id":"gpt-4o","weight":30}]' \
TIER_HARD_CONFIG='[{"provider":"bedrock","model_id":"anthropic.claude-sonnet-4-20250514-v1:0","weight":60},{"provider":"openai","model_id":"gpt-4o","weight":40}]' \
npx cdk deploy
```

**Per-target JSON fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `provider` | ✅ | `"bedrock"` or `"openai"` |
| `model_id` | ✅ | Model name/ID |
| `weight` | ✅ | Relative weight (1-100). 80:20 = 80% to first, 20% to second |
| `inference_profile` | ❌ | Bedrock cross-region profile (auto-derived if omitted) |
| `api_base` | ❌ | OpenAI-compatible base URL |
| `api_key` | ❌ | API key (or set via `TIER_{TIER}_API_KEY` env var) |
| `description` | ❌ | Human-readable label |

**Weights don't need to sum to 100.** Ratios work: `[3, 1]` = 75%/25%. Minimum weight is 1.

> **Note:** JSON env vars (`TIER_SIMPLE_CONFIG`) take priority over single-value env vars (`TIER_SIMPLE_PROVIDER`). Set one or the other.

## 📊 Monitoring

Deployed with:
- **CloudWatch Dashboard** — invocations by tier, latency (p50/p99), error rate
- **CloudWatch Alarms** — error rate > 5%, p99 latency > 30s
- **Cost estimation widget** — visual cost breakdown

## 🧪 Test Endpoints

```bash
export API_URL=$(aws cloudformation describe-stacks --stack-name MultiModelRouter \
  --query 'Stacks[0].Outputs[?OutputKey==`InvokeUrl`].OutputValue' --output text)

bash scripts/invoke_test.sh
```

## 🏗 Architecture

```
┌──────────┐    ┌──────────────┐    ┌─────────────┐    ┌───────────────────┐
│  Client   │───▶│ API Gateway  │───▶│   Lambda     │───▶│    Bedrock        │
│           │    │  HTTP API    │    │   Router     │    │  Cross-Region     │
└──────────┘    └──────────────┘    │  +Classifier  │    │  Inference        │
                                    └──────┬───────┘    │  Profiles         │
                                           │             └───────────────────┘
                                           ▼
                                    ┌──────────────┐
                                    │  CloudWatch  │
                                    │  Dashboard   │
                                    │  + Alarms    │
                                    └──────────────┘
```

**Cost savings estimation:** With ~70% of traffic routing to Haiku (Simple), ~20% to Sonnet 3.5 (Medium), and ~10% to Sonnet 4 (Hard), you save **~60%** vs. routing everything to the most expensive model.

## 🤝 Contributing

PRs welcome. Keep the classifier heuristic-based (no LLM calls for routing) and test for all 3 tiers.
