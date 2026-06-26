"""
Prompt complexity classifier.

Heuristics-based — no LLM call needed for routing decisions.
Classifies prompts into simple / medium / hard tiers based on:
  - Estimated token count
  - Code block indicators
  - Reasoning complexity markers
  - Structured output requirements
  - Multi-step instructions
"""

import re
from typing import Dict, Tuple

import config

# Markers that indicate higher complexity
CODE_INDICATORS = [
    "```", "def ", "class ",  "function", "=>",
    "import ", "#include", "package ", "module",
    "interface ", "type ", "const ", "let ",
]

REASONING_INDICATORS = [
    "explain", "why", "how does", "how would",
    "compare", "contrast", "analyze", "synthesize",
    "reason", "justify", "prove", "derive",
    "what if", "what's the difference",
    "implications", "root cause", "trade-off",
    "evaluate", "critique", "assess",
]

STRUCTURED_OUTPUT_INDICATORS = [
    "json", "yaml", "xml", "csv",
    "schema", "validate", "parse",
    "format as", "output as",
]

MULTI_STEP_INDICATORS = [
    "first", "then", "next", "finally",
    "step 1", "step 2", "step 3",
    "follow these steps",
    "do the following",
    "1.", "2.", "3.",
]


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough approximation: total chars / chars-per-token)."""
    return max(1, len(text) // config.CHARS_PER_TOKEN)


def count_markers(text: str, markers: list) -> int:
    """Count how many distinct markers appear in text."""
    text_lower = text.lower()
    return sum(1 for m in markers if m.lower() in text_lower)


def classify_prompt(prompt: str, system_prompt: str = "") -> Tuple[str, Dict]:
    """
    Classify a prompt into a routing tier.

    Returns (tier_name, explanation) where explanation contains
    the reasoning for the classification.
    """
    full_text = system_prompt + "\n" + prompt if system_prompt else prompt
    token_estimate = estimate_tokens(prompt)

    code_score = count_markers(full_text, CODE_INDICATORS)
    reasoning_score = count_markers(full_text, REASONING_INDICATORS)
    structured_score = count_markers(full_text, STRUCTURED_OUTPUT_INDICATORS)
    multi_step_score = count_markers(full_text, MULTI_STEP_INDICATORS)

    reasons = []

    # --- Hard tier: high complexity ---
    hard_triggers = []

    if code_score >= 3:
        hard_triggers.append(f"heavy code content ({code_score} markers)")
    if reasoning_score >= 3:
        hard_triggers.append(f"deep reasoning required ({reasoning_score} markers)")
    if multi_step_score >= 3:
        hard_triggers.append(f"multi-step instructions ({multi_step_score} markers)")
    if token_estimate > 3000:
        hard_triggers.append(f"very long input (~{token_estimate} tokens)")

    if token_estimate > 1000 and (code_score >= 1 or reasoning_score >= 2):
        hard_triggers.append(f"long input with analytical content (~{token_estimate} tokens)")

    if len(hard_triggers) >= 1:
        reasons = hard_triggers
        return "hard", {
            "tier": "hard",
            "reason": "; ".join(reasons),
            "token_estimate": token_estimate,
            "scores": {
                "code": code_score,
                "reasoning": reasoning_score,
                "structured": structured_score,
                "multi_step": multi_step_score,
            },
        }

    # --- Medium tier: moderate complexity ---
    medium_triggers = []

    if code_score >= 1:
        medium_triggers.append(f"code presence ({code_score} markers)")
    if reasoning_score >= 1:
        medium_triggers.append(f"analysis/reasoning requested ({reasoning_score} markers)")
    if structured_score >= 1:
        medium_triggers.append(f"structured output required ({structured_score} markers)")
    if multi_step_score >= 1:
        medium_triggers.append(f"multi-step indicators ({multi_step_score} markers)")
    if 200 < token_estimate <= 1000:
        medium_triggers.append(f"moderate length (~{token_estimate} tokens)")

    if len(medium_triggers) >= 1:
        reasons = medium_triggers
        return "medium", {
            "tier": "medium",
            "reason": "; ".join(reasons),
            "token_estimate": token_estimate,
            "scores": {
                "code": code_score,
                "reasoning": reasoning_score,
                "structured": structured_score,
                "multi_step": multi_step_score,
            },
        }

    # --- Simple tier: low complexity ---
    return "simple", {
        "tier": "simple",
        "reason": f"low complexity, short input (~{token_estimate} tokens)",
        "token_estimate": token_estimate,
        "scores": {
            "code": code_score,
            "reasoning": reasoning_score,
            "structured": structured_score,
            "multi_step": multi_step_score,
        },
    }
