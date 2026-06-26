# ⟁ Critical Operations AI Model Router

Reduce **provider concentration risk** for APRA-regulated critical operations by load-balancing inference across frontier models. Built on AWS Bedrock with native cross-region inference.

```
                          ┌── Simple: Claude 3.5 Haiku (80%)
👤→⚡→🧠→🔀──┼── Medium: Claude Sonnet 4 (15%) ──→ ✅
                          └── Complex: Claude Opus 4.8 (5%)
```

## 🎯 Why

APRA's **CPS 230** (Operational Resilience Management) requires regulated entities to identify and manage operational risks to **critical operations** — business operations whose disruption would materially impact financial stability or customer outcomes.

A single-model dependency creates **provider concentration risk**:
- Model outage → critical operation disruption
- Provider price change → unexpected cost exposure
- Single failure domain → no fallback path

This router **eliminates single-model concentration risk** by:
1. **Classifying** prompts by complexity (Simple / Medium / Complex)
2. **Load balancing** across multiple models/providers with weighted targets
3. **Cross-region inference** via Bedrock for availability zone resilience
4. **Audit trail** — every request logs tier, provider, model, latency, tokens

### Use Case: Retail Banking Deposit Taking

A retail bank's deposit-taking process is a **critical operation** under CPS 230. When AI assists with:
- Customer identity verification
- Deposit account queries
- Transaction dispute analysis
- Regulatory reporting

The router ensures no single model failure halts the operation. If Claude Opus 4.8 is unavailable, traffic seamlessly fails over to GPT-5.5 or Kimi K2.5.

## 🏗 Architecture

| Tier | Default Model | Default Provider | Weight | Cross-Region |
|------|--------------|-----------------|--------|-------------|
| **Simple** | Claude 3.5 Haiku | Bedrock | 80% | `us.anthropic.claude-3-5-haiku-...` |
| **Medium** | Claude Sonnet 4 | Bedrock | 15% | `us.anthropic.claude-sonnet-4-...` |
| **Complex** | Claude Opus 4.8 | Bedrock | 5% | `us.anthropic.claude-opus-4-8` |

Each tier is **independently configurable** — swap providers, models, or weights per tier.

## 🚀 One-Click Deploy

```bash
git clone https://github.com/kdeath83/critical-ops-ai-model-router
cd critical-ops-ai-model-router

# Deploy via CDK (requires AWS credentials + Bedrock model access)
npm install
npx cdk bootstrap
npx cdk deploy --require-approval never

# Or use the script
bash scripts/deploy.sh
```

### Prerequisites

- AWS CLI v2
- Node.js 20+
- Bedrock model access enabled (Claude 3.5 Haiku, Sonnet 4, Opus 4.8)
- Python 3.12+ (for Lambda runtime)

## 🖥️ Frontend Dashboard

Deployed via S3 + CloudFront as part of the stack, or accessible directly:

**GitHub Pages:** https://kdeath83.github.io/critical-ops-ai-model-router/

Open in demo mode (click Simulate) or connect to your live API (click **🔌 Live**).

### Dashboard Features

- **Animated pipeline** with branching tier lanes and Matrix-style flow visualization
- **Killswitch** — red button to gracefully stop all in-flight requests
- **Live mode** — connect to your deployed API endpoint
- **Per-tier stats** + 30s rolling chart + provider donut split
- **Request log** with full routing metadata (click any row for detail modal)

## 📡 API

### `POST /invoke`

```bash
curl -X POST https://<api-endpoint>/invoke \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Verify customer identity for deposit account", "tier": "auto"}'
```

### `GET /health`

```json
{"status": "healthy", "tiers": ["simple", "medium", "complex"], "region": "us-east-1"}
```

## ⚖️ Load Balancing

Each tier supports **multiple targets** with **weighted random selection**.

```bash
# Simple tier: 80% Bedrock Claude 3.5 Haiku, 20% OpenAI GPT-5.5
TIER_SIMPLE_CONFIG='[
  {"provider":"bedrock","model_id":"anthropic.claude-3-5-haiku-20241022-v1:0","weight":80},
  {"provider":"openai","model_id":"gpt-5.5","weight":20}
]' npx cdk deploy
```

Weights are ratios — they don't need to sum to 100. `[3, 1]` = 75%/25%.

### Available Providers

| Provider | Endpoint | Models |
|----------|----------|--------|
| `bedrock` | Converse API | Claude, Kimi K2.5, Llama, Mistral, DeepSeek |
| `openai` | OpenAI-compatible API | OpenAI, Kimi (via API key), Azure OpenAI |

## 🗺️ Region Configuration

Control cross-region inference geography via env var:

```bash
AWS_GEOGRAPHY=eu bash scripts/deploy.sh   # European regions
AWS_GEOGRAPHY=ap bash scripts/deploy.sh   # Asia Pacific
```

Geography auto-detects from deployment region. Supported:

| Geography | Regions |
|-----------|---------|
| `us` (default) | us-east-1, us-east-2, us-west-2 |
| `eu` | eu-west-1/2/3, eu-central-1, eu-north-1 |
| `ap` | ap-northeast-1/2/3, ap-southeast-1/2/3, ap-south-1 |

## 🛡️ CPS 230 Compliance Mapping

| CPS 230 Requirement | How This Router Addresses It |
|---------------------|-----------------------------|
| Identify critical operations | Tier classification maps prompt complexity to operational criticality |
| Manage operational risk | Multi-provider load balancing eliminates single points of failure |
| Maintain resilience | Cross-region inference provides availability zone redundancy |
| Scenario testing | Configurable weights let you test failover behaviour |
| Board reporting | Request log provides full audit trail (tier, provider, model, latency) |

## 🔧 Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_GEOGRAPHY` | auto | `us`, `eu`, or `ap` |
| `TIER_{TIER}_PROVIDER` | `bedrock` | `bedrock` or `openai` |
| `TIER_{TIER}_MODEL_ID` | (tier default) | Model name/ID |
| `TIER_{TIER}_CONFIG` | — | JSON array of targets for load balancing |
| `TIER_{TIER}_API_KEY` | — | API key for OpenAI-compatible providers |
| `CORS_ORIGIN` | `*` | Allowed CORS origin (set to CloudFront URL in prod) |

### Default Model IDs

| Variable | Default |
|----------|---------|
| `TIER_SIMPLE_MODEL_ID` | `anthropic.claude-3-5-haiku-20241022-v1:0` |
| `TIER_MEDIUM_MODEL_ID` | `anthropic.claude-sonnet-4-20250514-v1:0` |
| `TIER_COMPLEX_MODEL_ID` | `anthropic.claude-opus-4-8` |

> Note: The internal tier key remains `"hard"` for backward compatibility. The display label is "Complex".

## 📊 Monitoring

Deployed with CloudWatch dashboard + alarms:
- Invocations & Errors (total count)
- Latency (p50, p99) and throttles
- Cost estimation widget
- Alarm: error rate > 5%, p99 latency > 30s

## 🧪 Running Tests

```bash
cd critical-ops-ai-model-router
python3 -m pytest test/ -v
```

30 tests covering classifier heuristics, Bedrock + OpenAI routing, weighted load balancing (80:20, 50:30:20, 3:1 distributions).

## 📁 Project Structure

```
├── lambda-router/          # Lambda backend
│   ├── index.py            # API handler
│   ├── classifier.py       # Prompt complexity classifier
│   ├── router.py           # Model routing + load balancing
│   └── config.py           # Tier configuration
├── lib/                    # CDK infrastructure
│   └── multi-model-router-stack.ts
├── frontend/               # Dashboard (HTML + JS + Canvas)
├── test/                   # 30 unit tests
└── scripts/                # Deploy + test scripts
```

## 🔐 API Keys

For production, store provider API keys in **AWS Secrets Manager** and reference them in the Lambda environment. The env-var approach is suitable for dev/demo.

## 📄 License

MIT
