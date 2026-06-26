"""
Inference router — selects a target (weighted) and dispatches to provider.

Supports:
  - Bedrock   (Converse API, with cross-region inference profiles)
  - OpenAI    (OpenAI-compatible: OpenAI, Kimi, Azure OpenAI, etc.)

Each tier can have multiple targets with weighted load balancing.
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

import boto3

import config
from config import select_target

logger = logging.getLogger()


# ─── OpenAI-compatible client ──────────────────────────────


def _openai_chat_completion(
    api_base: str,
    api_key: str,
    model: str,
    messages: list,
    temperature: float,
    max_tokens: int,
    system_prompt: str = "",
) -> Dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body: Dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if system_prompt:
        body["messages"].insert(0, {"role": "system", "content": system_prompt})

    url = f"{api_base.rstrip('/')}/chat/completions"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_openai_response(result: Dict) -> str:
    choices = result.get("choices", [])
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "")


def _openai_usage(result: Dict) -> Dict:
    u = result.get("usage", {})
    return {
        "input_tokens": u.get("prompt_tokens", 0),
        "output_tokens": u.get("completion_tokens", 0),
        "total_tokens": u.get("total_tokens", 0),
    }


# ─── Bedrock client ────────────────────────────────────────


def _build_converse_body(prompt: str, system_prompt: str, temperature: float, max_tokens: int) -> Dict:
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    body: Dict[str, Any] = {
        "messages": messages,
        "inferenceConfig": {"temperature": temperature, "maxTokens": max_tokens},
    }
    if system_prompt:
        body["system"] = [{"text": system_prompt}]
    return body


def _invoke_bedrock_profile(client: Any, profile_id: str, body: Dict, model_id: str) -> Dict:
    """Try cross-region inference profile, fall back to direct model invocation."""
    try:
        resp = client.converse(
            modelId=profile_id,
            messages=body["messages"],
            system=body.get("system", []),
            inferenceConfig=body["inferenceConfig"],
        )
        return {"mode": "profile", "response": resp, "profile_id": profile_id}
    except client.exceptions.AccessDeniedException:
        # Access denied is not a profile issue — re-raise
        raise
    except client.exceptions.ValidationException as e:
        # Profile doesn't exist or invalid — try direct
        logger.warning("Profile invocation failed, falling back to direct: %s", e)
    except Exception as e:
        logger.warning("Profile invocation error, falling back to direct: %s", e)

    resp = client.converse(
        modelId=model_id,
        messages=body["messages"],
        system=body.get("system", []),
        inferenceConfig=body["inferenceConfig"],
    )
    return {"mode": "direct", "response": resp, "model_id": model_id}


def _parse_bedrock_response(result: Dict) -> str:
    output = result.get("output", {})
    message = output.get("message", {})
    content = message.get("content", [])
    texts = [b.get("text", "") for b in content if "text" in b]
    return "\n".join(texts)


def _bedrock_usage(result: Dict) -> Dict:
    u = result.get("usage", {})
    return {
        "input_tokens": u.get("inputTokens", 0),
        "output_tokens": u.get("outputTokens", 0),
        "total_tokens": u.get("totalTokens", 0),
    }


# ─── Main dispatch ─────────────────────────────────────────


def route_inference(
    prompt: str,
    tier_name: str,
    system_prompt: str = "",
    temperature: Optional[float] = None,
    max_tokens: Optional[float] = None,
    force_direct: bool = False,
) -> Dict:
    """
    Route inference: select a target (weighted), dispatch to its provider.
    Returns dict with keys: response, routing, usage, model_config.
    """
    target = select_target(tier_name)

    temp = temperature if temperature is not None else 0.5
    mtok = max_tokens if max_tokens is not None else 2048
    start = time.time()

    provider = target["provider"]
    try:
        if provider == "bedrock":
            result = _route_bedrock(prompt, tier_name, target, system_prompt, temp, mtok, force_direct)
        elif provider == "openai":
            result = _route_openai(prompt, tier_name, target, system_prompt, temp, mtok)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    except Exception:
        logger.exception("Routing failed for tier=%s provider=%s", tier_name, provider)
        raise

    elapsed_ms = int((time.time() - start) * 1000)
    result["routing"]["latency_ms"] = elapsed_ms
    result["routing"]["lb_weight"] = target["weight"]
    result["lb_targets"] = [
        {"provider": t["provider"], "model_id": t["model_id"], "weight": t["weight"]}
        for t in config.get_tier(tier_name)["targets"]
    ]

    return result


# ─── Bedrock routing ───────────────────────────────────────


def _route_bedrock(
    prompt: str,
    tier_name: str,
    target: Dict,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
    force_direct: bool,
) -> Dict:
    client = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)
    body = _build_converse_body(prompt, system_prompt, temperature, max_tokens)

    if force_direct or not target.get("inference_profile"):
        resp = client.converse(
            modelId=target["model_id"],
            messages=body["messages"],
            system=body.get("system", []),
            inferenceConfig=body["inferenceConfig"],
        )
        invoke_result = {"mode": "direct", "response": resp}
    else:
        invoke_result = _invoke_bedrock_profile(client, target["inference_profile"], body, target["model_id"])

    convo = invoke_result["response"]
    response_text = _parse_bedrock_response(convo)
    usage = _bedrock_usage(convo)
    metrics = convo.get("metrics", {})

    return {
        "response": response_text,
        "routing": {
            "tier": tier_name,
            "provider": "bedrock",
            "model_id": target["model_id"],
            "inference_profile": target.get("inference_profile") if invoke_result["mode"] == "profile" else None,
            "mode": invoke_result["mode"],
            "model_latency_ms": metrics.get("latencyMs", 0),
            "region": config.AWS_REGION,
        },
        "usage": usage,
        "model_config": {
            "provider": "bedrock",
            "description": target.get("description", ""),
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    }


# ─── OpenAI-compatible routing ─────────────────────────────


def _route_openai(
    prompt: str,
    tier_name: str,
    target: Dict,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
) -> Dict:
    api_key = target.get("api_key") or ""
    api_base = target.get("api_base") or "https://api.openai.com/v1"

    if not api_key:
        return {
            "response": (
                f"Error: No API key configured for {target['model_id']}. "
                f"Set TIER_{tier_name.upper()}_API_KEY or use Secrets Manager."
            ),
            "routing": {"tier": tier_name, "provider": "openai", "error": "missing_api_key"},
            "usage": {},
            "model_config": {"provider": "openai"},
        }

    messages = [{"role": "user", "content": prompt}]
    result = _openai_chat_completion(
        api_base=api_base, api_key=api_key, model=target["model_id"],
        messages=messages, temperature=temperature, max_tokens=int(max_tokens),
        system_prompt=system_prompt,
    )

    response_text = _parse_openai_response(result)
    usage = _openai_usage(result)

    return {
        "response": response_text,
        "routing": {
            "tier": tier_name,
            "provider": "openai",
            "model_id": target["model_id"],
        },
        "usage": usage,
        "model_config": {
            "provider": "openai",
            "description": target.get("description", ""),
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    }
