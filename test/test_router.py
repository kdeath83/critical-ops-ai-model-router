"""
Router unit tests — Bedrock and OpenAI providers.
Tests use mocked clients and mocked select_target for isolation.
"""
import json
import sys
import os
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda-router"))

import config
from router import (
    _build_converse_body,
    _parse_bedrock_response,
    _parse_openai_response,
    _openai_usage,
    _bedrock_usage,
)


# ─── Bedrock helpers ───────────────────────────────────────


def test_build_converse_body_basic():
    body = _build_converse_body(prompt="Hello", system_prompt="", temperature=0.5, max_tokens=100)
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][0]["content"][0]["text"] == "Hello"
    assert body["inferenceConfig"]["temperature"] == 0.5
    assert body["inferenceConfig"]["maxTokens"] == 100
    assert "system" not in body


def test_build_converse_body_with_system():
    body = _build_converse_body(prompt="Hello", system_prompt="Be helpful", temperature=0.5, max_tokens=100)
    assert body["system"][0]["text"] == "Be helpful"


def test_parse_bedrock_response_basic():
    result = {
        "stopReason": "end_turn",
        "output": {"message": {"content": [{"text": "Hello world"}]}},
        "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        "metrics": {"latencyMs": 200},
    }
    assert _parse_bedrock_response(result) == "Hello world"


def test_parse_bedrock_response_multiple():
    result = {"output": {"message": {"content": [{"text": "A. "}, {"text": "B."}]}}}
    assert _parse_bedrock_response(result) == "A. \nB."


def test_bedrock_usage():
    result = {"usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}}
    u = _bedrock_usage(result)
    assert u["input_tokens"] == 10
    assert u["output_tokens"] == 5


# ─── OpenAI helpers ────────────────────────────────────────


def test_parse_openai_response():
    result = {"choices": [{"message": {"content": "Hello from OpenAI"}}]}
    assert _parse_openai_response(result) == "Hello from OpenAI"


def test_parse_openai_response_empty():
    assert _parse_openai_response({}) == ""


def test_openai_usage():
    result = {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    u = _openai_usage(result)
    assert u["input_tokens"] == 10
    assert u["output_tokens"] == 5


# ─── Mock helpers ──────────────────────────────────────────


def _mock_bedrock_target(tier="simple"):
    """Simulate a target config returned by select_target for Bedrock."""
    t = config.TIERS[tier]["targets"][0]
    return {
        "provider": "bedrock",
        "model_id": t["model_id"],
        "weight": 100,
        "inference_profile": t["inference_profile"],
        "api_base": None,
        "api_key": None,
        "description": "test",
    }


def _mock_openai_target(model_id="gpt-4o-mini", api_key="sk-test"):
    return {
        "provider": "openai",
        "model_id": model_id,
        "weight": 100,
        "inference_profile": None,
        "api_base": "https://api.openai.com/v1",
        "api_key": api_key,
        "description": "test openai",
    }


# ─── Bedrock routing ───────────────────────────────────────


@patch("router.boto3.client")
@patch("router.select_target")
def test_route_inference_bedrock_direct(mock_select, mock_boto_client):
    """Bedrock direct mode (no inference profile)."""
    mock_select.return_value = _mock_bedrock_target()

    mock_converse = MagicMock()
    mock_converse.return_value = {
        "stopReason": "end_turn",
        "output": {"message": {"content": [{"text": "Paris"}]}},
        "usage": {"inputTokens": 5, "outputTokens": 1, "totalTokens": 6},
        "metrics": {"latencyMs": 100},
    }
    mock_client = MagicMock()
    mock_client.converse = mock_converse
    mock_boto_client.return_value = mock_client

    from router import route_inference
    result = route_inference(
        prompt="What is the capital of France?",
        tier_name="simple",
        force_direct=True,
    )

    assert result["response"] == "Paris"
    assert result["routing"]["tier"] == "simple"
    assert result["routing"]["provider"] == "bedrock"
    assert result["routing"]["mode"] == "direct"


@patch("router.boto3.client")
@patch("router.select_target")
def test_route_inference_bedrock_profile(mock_select, mock_boto_client):
    """Bedrock with cross-region inference profile."""
    mock_select.return_value = _mock_bedrock_target("medium")

    mock_converse = MagicMock()
    mock_converse.return_value = {
        "stopReason": "end_turn",
        "output": {"message": {"content": [{"text": "Analysis"}]}},
        "usage": {"inputTokens": 50, "outputTokens": 30, "totalTokens": 80},
        "metrics": {"latencyMs": 500},
    }
    mock_client = MagicMock()
    mock_client.converse = mock_converse
    mock_boto_client.return_value = mock_client

    from router import route_inference
    result = route_inference(
        prompt="Analyze this",
        tier_name="medium",
    )

    call_kwargs = mock_converse.call_args[1]
    profile = config.TIERS["medium"]["targets"][0]["inference_profile"]
    assert call_kwargs["modelId"] == profile
    assert result["routing"]["mode"] == "profile"
    assert result["routing"]["provider"] == "bedrock"


# ─── OpenAI routing ────────────────────────────────────────


@patch("router.urllib.request.urlopen")
@patch("router.select_target")
def test_route_inference_openai(mock_select, mock_urlopen):
    """OpenAI provider with mocked HTTP response."""
    mock_select.return_value = _mock_openai_target()

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "choices": [{"message": {"content": "Hello from GPT"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    from router import route_inference
    result = route_inference(
        prompt="Say hello",
        tier_name="medium",
    )

    assert result["response"] == "Hello from GPT"
    assert result["routing"]["provider"] == "openai"
    assert result["routing"]["tier"] == "medium"
    assert result["routing"]["model_id"] == "gpt-4o-mini"
    assert result["usage"]["input_tokens"] == 10


@patch("router.urllib.request.urlopen")
@patch("router.select_target")
def test_route_inference_openai_kimi(mock_select, mock_urlopen):
    """Kimi (Moonshot) via OpenAI-compatible endpoint."""
    mock_select.return_value = _mock_openai_target(
        model_id="moonshot-v1-8k",
        api_key="sk-kimi-test",
    )
    mock_select.return_value["api_base"] = "https://api.moonshot.cn/v1"

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "choices": [{"message": {"content": "Kimi response"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    from router import route_inference
    result = route_inference(
        prompt="Hello Kimi",
        tier_name="hard",
    )

    assert result["response"] == "Kimi response"
    assert result["routing"]["provider"] == "openai"
    assert result["routing"]["model_id"] == "moonshot-v1-8k"
    call_args = mock_urlopen.call_args[0][0]
    assert "api.moonshot.cn" in str(call_args.full_url)


@patch("router.select_target")
def test_route_inference_openai_missing_key(mock_select):
    """OpenAI provider with no API key should return error."""
    mock_select.return_value = _mock_openai_target(api_key="")

    from router import route_inference
    result = route_inference(
        prompt="Hello",
        tier_name="simple",
    )
    assert "Error" in result["response"]
    assert result["routing"]["error"] == "missing_api_key"
