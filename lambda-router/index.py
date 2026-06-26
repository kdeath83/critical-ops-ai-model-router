"""
AWS Lambda handler for the Multi-Model LLM Router.

Entry point: lambda_handler(event, context)
API: POST /invoke — route a prompt to the appropriate model tier
     GET  /health — health check
"""

import json
import logging
import traceback
from typing import Dict, Any

from classifier import classify_prompt
from router import route_inference
import config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Max request body size (256 KB)
MAX_BODY_SIZE = 256 * 1024

# Allowed origin for CORS — set to your CloudFront domain in production
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "*")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    API Gateway Lambda proxy integration handler.
    Accepts both HTTP API and REST API formats.
    """
    http_method = (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method", "")
        or event.get("routeKey", "").split(" ")[0]
    )

    # --- Health check ---
    if http_method == "GET":
        return _health_response()

    # --- POST /invoke ---
    try:
        raw_body = event.get("body", "{}")
        if isinstance(raw_body, str) and len(raw_body) > MAX_BODY_SIZE:
            return _error_response(413, "Request body too large")

        body = raw_body
        if isinstance(body, str):
            body = json.loads(body)

        prompt = body.get("prompt", "").strip()
        if not prompt:
            return _error_response(400, "Missing required field: 'prompt'")

        system_prompt = body.get("system_prompt", "").strip()
        requested_tier = body.get("tier", "auto")
        temperature = body.get("temperature")
        max_tokens = body.get("max_tokens")

        # --- Classify prompt complexity ---
        if requested_tier == "auto" or requested_tier not in config.TIERS:
            tier_name, classification = classify_prompt(prompt, system_prompt)
        else:
            tier_name = requested_tier
            classification = {
                "tier": requested_tier,
                "reason": "user-specified tier override",
                "token_estimate": len(prompt) // config.CHARS_PER_TOKEN,
                "scores": {},
            }

        # --- Route to model ---
        result = route_inference(
            prompt=prompt,
            tier_name=tier_name,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            force_direct=body.get("force_direct", False),
        )

        return {
            "statusCode": 200,
            "headers": _cors_headers(),
            "body": json.dumps({
                "success": True,
                "response": result["response"],
                "routing": result["routing"],
                "usage": result["usage"],
                "classification": classification,
                "model": result["model_config"],
            }),
        }

    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON: %s", e)
        return _error_response(400, "Invalid JSON body")
    except ValueError as e:
        logger.warning("Bad request: %s", e)
        return _error_response(400, str(e))
    except Exception:
        logger.exception("Internal error processing request")
        return _error_response(500, "Internal server error")


def _cors_headers() -> Dict:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": CORS_ORIGIN,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Api-Key, Authorization",
    }


def _health_response() -> Dict:
    return {
        "statusCode": 200,
        "headers": _cors_headers(),
        "body": json.dumps({
            "status": "healthy",
            "tiers": list(config.TIERS.keys()),
            "region": config.AWS_REGION,
        }),
    }


def _error_response(status_code: int, message: str) -> Dict:
    return {
        "statusCode": status_code,
        "headers": _cors_headers(),
        "body": json.dumps({
            "success": False,
            "error": message,
        }),
    }
