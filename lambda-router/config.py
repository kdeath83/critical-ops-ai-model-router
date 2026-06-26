"""
Model tier configuration for the multi-model LLM router.

Each tier (simple / medium / hard) supports MULTIPLE targets with
weighted load balancing.  Default: single target (Bedrock, 100%).

Configure targets via JSON environment variable:
  TIER_SIMPLE_CONFIG='[
    {"provider":"bedrock","model_id":"...","weight":80},
    {"provider":"openai","model_id":"gpt-4o-mini","weight":20}
  ]'

The old single-provider format (TIER_SIMPLE_PROVIDER, TIER_SIMPLE_MODEL_ID,
etc.) is still supported — it creates a single target with weight 100.
"""

import json
import os
import random
from typing import Dict, List, Optional, TypedDict


# ─── Types ──────────────────────────────────────────────

class TargetConfig(TypedDict):
    provider: str            # "bedrock" | "openai"
    model_id: str
    weight: int              # 1-100; relative weight for load balancing
    inference_profile: Optional[str]  # Bedrock only
    api_base: Optional[str]           # OpenAI-compatible only
    api_key: Optional[str]            # OpenAI-compatible only
    description: str


class TierConfig(TypedDict):
    targets: List[TargetConfig]


# ─── Geography resolution ──────────────────────────────

_GEOGRAPHY_MAP: Dict[str, str] = {
    "us-east-1": "us", "us-east-2": "us", "us-west-2": "us",
    "eu-west-1": "eu", "eu-west-2": "eu", "eu-west-3": "eu",
    "eu-central-1": "eu", "eu-north-1": "eu",
    "ap-northeast-1": "ap", "ap-northeast-2": "ap",
    "ap-northeast-3": "ap", "ap-southeast-1": "ap",
    "ap-southeast-2": "ap", "ap-southeast-3": "ap",
    "ap-south-1": "ap",
}

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_GEOGRAPHY = (os.getenv("AWS_GEOGRAPHY") or _GEOGRAPHY_MAP.get(AWS_REGION, "us")).lower()
GEO_PREFIX = f"{AWS_GEOGRAPHY}."

# How many chars ≈ 1 token
CHARS_PER_TOKEN = 4


# ─── Helpers ────────────────────────────────────────────

def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _inference_profile(model_id: str) -> str:
    return f"{GEO_PREFIX}{model_id}"


# ─── Target builders ────────────────────────────────────

_DEFAULT_MODELS = {
    "simple": "anthropic.claude-3-5-haiku-20241022-v1:0",
    "medium": "anthropic.claude-sonnet-4-20250514-v1:0",
    "hard": "anthropic.claude-opus-4-8",
}

_DEFAULT_MAX_TOKENS = {"simple": 1024, "medium": 2048, "hard": 8192}
_DEFAULT_TEMPERATURE = {"simple": 0.1, "medium": 0.3, "hard": 0.5}
_DEFAULT_DESCRIPTIONS = {
    "simple": "Fast, cheap — Claude 3.5 Haiku, GPT-5.5 mini",
    "medium": "Balanced — Claude Sonnet 4, GPT-5.5",
    "hard": "Maximum reasoning — Claude Opus 4.8, GPT-5.5 Pro",
}


def _build_single_target(tier: str) -> TargetConfig:
    """Build a single Bedrock target from old-style env vars."""
    prefix = f"TIER_{tier.upper()}"
    model_id = _env(f"{prefix}_MODEL_ID", _DEFAULT_MODELS[tier])
    explicit_profile = _env(f"{prefix}_INFERENCE_PROFILE")
    provider_raw = _env(f"{prefix}_PROVIDER", "bedrock").lower()

    if provider_raw == "openai":
        return {
            "provider": "openai",
            "model_id": model_id,
            "weight": 100,
            "inference_profile": None,
            "api_base": _env(f"{prefix}_API_BASE", "https://api.openai.com/v1"),
            "api_key": _env(f"{prefix}_API_KEY", ""),
            "description": _DEFAULT_DESCRIPTIONS[tier],
        }

    return {
        "provider": "bedrock",
        "model_id": model_id,
        "weight": 100,
        "inference_profile": explicit_profile or _inference_profile(model_id),
        "api_base": None,
        "api_key": None,
        "description": _DEFAULT_DESCRIPTIONS[tier],
    }


def _build_multi_targets(tier: str, config_json: str) -> List[TargetConfig]:
    """Build multiple targets from JSON config string."""
    try:
        raw = json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        return []

    targets = []
    for item in raw:
        provider = item.get("provider", "bedrock").lower()
        model_id = item.get("model_id", _DEFAULT_MODELS[tier])
        weight = int(item.get("weight", 100))
        desc = item.get("description", _DEFAULT_DESCRIPTIONS[tier])

        if provider == "openai":
            targets.append({
                "provider": "openai",
                "model_id": model_id,
                "weight": max(1, weight),
                "inference_profile": None,
                "api_base": item.get("api_base", "https://api.openai.com/v1"),
                "api_key": item.get("api_key", _env(f"TIER_{tier.upper()}_API_KEY", "")),
                "description": desc,
            })
        else:
            explicit_profile = item.get("inference_profile")
            targets.append({
                "provider": "bedrock",
                "model_id": model_id,
                "weight": max(1, weight),
                "inference_profile": explicit_profile or _inference_profile(model_id),
                "api_base": None,
                "api_key": None,
                "description": desc,
            })

    return targets


def _resolve_tier(tier: str) -> TierConfig:
    """Resolve a tier's configuration (multi-target JSON > single-target env vars > default)."""
    config_json = _env(f"TIER_{tier.upper()}_CONFIG", "")
    if config_json:
        targets = _build_multi_targets(tier, config_json)
        if targets:
            return {"targets": targets}

    # Fall back to single-target (env vars or default)
    return {"targets": [_build_single_target(tier)]}


# ─── Tier definitions ──────────────────────────────────

TIERS: Dict[str, TierConfig] = {
    "simple": _resolve_tier("simple"),
    "medium": _resolve_tier("medium"),
    "hard": _resolve_tier("hard"),
}


# ─── Public API ─────────────────────────────────────────

def get_tier(tier_name: str) -> TierConfig:
    if tier_name not in TIERS:
        raise ValueError(f"Unknown tier '{tier_name}'. Valid: {list(TIERS.keys())}")
    return TIERS[tier_name]


def select_target(tier_name: str) -> TargetConfig:
    """Weighted random selection from a tier's targets."""
    tier = get_tier(tier_name)
    targets = tier["targets"]
    if len(targets) == 1:
        return targets[0]

    total = sum(t["weight"] for t in targets)
    r = random.uniform(0, total)
    for t in targets:
        r -= t["weight"]
        if r <= 0:
            return t
    return targets[-1]  # safety


def get_supported_regions() -> list:
    _REGIONS = {
        "us": ["us-east-1", "us-east-2", "us-west-2"],
        "eu": ["eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-north-1"],
        "ap": [
            "ap-northeast-1", "ap-northeast-2", "ap-northeast-3",
            "ap-southeast-1", "ap-southeast-2", "ap-southeast-3",
            "ap-south-1",
        ],
    }
    return _REGIONS.get(AWS_GEOGRAPHY, [])
