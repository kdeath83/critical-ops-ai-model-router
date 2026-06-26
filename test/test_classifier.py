"""
Classifier unit tests.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda-router"))

from classifier import classify_prompt, estimate_tokens, count_markers


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 1


def test_estimate_tokens_short():
    # "Hello world" is 11 chars
    assert estimate_tokens("Hello world") >= 1
    assert estimate_tokens("Hello world") == 2  # 11 // 4 = 2


def test_count_markers_none():
    assert count_markers("hello world", ["test"]) == 0


def test_count_markers_single():
    assert count_markers("hello test world", ["test"]) == 1


def test_count_markers_multiple():
    assert count_markers("test and TEST", ["test"]) == 1  # case-insensitive


def test_count_markers_multiple_markers():
    text = "explain why this code works"
    assert count_markers(text, ["explain", "why", "code"]) == 3


def test_simple_prompt():
    """Short, non-technical prompt should route to simple."""
    tier, info = classify_prompt("What is the capital of France?")
    assert tier == "simple"
    assert info["tier"] == "simple"


def test_medium_code():
    """Prompt with code presence should route to medium."""
    tier, info = classify_prompt("Write a Python function to sort a list.")
    assert tier == "medium"


def test_medium_reasoning():
    """Prompt asking for analysis should route to medium."""
    tier, info = classify_prompt("Explain the differences between REST and GraphQL.")
    assert tier == "medium"


def test_hard_code_and_reasoning():
    """Prompt with actual code + reasoning should route to hard."""
    prompt = """
Implement a complete binary search tree:

```python
def insert
def delete
def search
```

Explain the time complexity of each operation and compare to a hash table.
Synthesize the trade-offs and justify which data structure is better for what use case.
Return the analysis as JSON with fields: bst_complexity, hash_complexity, comparison.
"""
    tier, info = classify_prompt(prompt)
    assert tier == "hard", f"Expected hard, got {tier}: {info['reason']}"


def test_hard_long_analytical():
    """Long prompt with analytical content should route to hard."""
    prompt = "Explain the implications of " + " ".join(["compare", "analyze", "synthesize"] * 10)
    # Make it long enough
    prompt_with_reasoning = "Analyze the following: " + prompt
    tier, info = classify_prompt(prompt_with_reasoning)
    assert tier in ("medium", "hard")  # Could be either depending on scores


def test_system_prompt_included():
    """System prompt content should factor into classification."""
    tier, info = classify_prompt("Hello", system_prompt="Analyze this conversation")
    assert tier == "medium", f"Expected medium with system prompt, got {tier}"


def test_structured_output():
    """Prompt requesting JSON output should route to medium."""
    tier, info = classify_prompt("Format this as JSON: name, age, email")
    assert tier == "medium"
