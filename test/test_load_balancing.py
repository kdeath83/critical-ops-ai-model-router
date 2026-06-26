"""
Load balancing tests for select_target weighted random selection.
"""
import sys
import os
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda-router"))

from config import select_target, TIERS


def test_select_target_single():
    """Single target should always return that target."""
    t = select_target("simple")
    assert t["provider"] == "bedrock"
    assert t["weight"] == 100


def test_select_target_weighted():
    """Multi-target with 80:20 weights should approximate that distribution."""
    # Kick off multi-target mode via env
    os.environ["TIER_SIMPLE_CONFIG"] = (
        '[{"provider":"bedrock","model_id":"model-a","weight":80},'
        '{"provider":"openai","model_id":"model-b","weight":20}]'
    )
    # Reimport config to pick up env var
    import importlib
    import config
    importlib.reload(config)

    results = Counter()
    n = 10000
    for _ in range(n):
        t = config.select_target("simple")
        results[t["model_id"]] += 1

    # Should be approximately 80:20
    total = results["model-a"] + results["model-b"]
    pct_a = results["model-a"] / total * 100
    assert 75 < pct_a < 85, f"Expected ~80%, got {pct_a:.1f}%"

    # Cleanup
    del os.environ["TIER_SIMPLE_CONFIG"]
    importlib.reload(config)


def test_select_target_three_way():
    """Three targets with 50:30:20 distribution."""
    os.environ["TIER_MEDIUM_CONFIG"] = (
        '[{"provider":"bedrock","model_id":"m1","weight":50},'
        '{"provider":"openai","model_id":"m2","weight":30},'
        '{"provider":"openai","model_id":"m3","weight":20}]'
    )
    import importlib
    import config
    importlib.reload(config)

    results = Counter()
    n = 20000
    for _ in range(n):
        t = config.select_target("medium")
        results[t["model_id"]] += 1

    total = sum(results.values())
    pcts = {k: v/total*100 for k, v in results.items()}
    assert 45 < pcts["m1"] < 55, f"m1: {pcts['m1']:.1f}%"
    assert 25 < pcts["m2"] < 35, f"m2: {pcts['m2']:.1f}%"
    assert 15 < pcts["m3"] < 25, f"m3: {pcts['m3']:.1f}%"

    del os.environ["TIER_MEDIUM_CONFIG"]
    importlib.reload(config)


def test_select_target_uneven_weights():
    """Uneven weights that don't sum to 100 (e.g. 3:1)."""
    os.environ["TIER_HARD_CONFIG"] = (
        '[{"provider":"bedrock","model_id":"x","weight":3},'
        '{"provider":"openai","model_id":"y","weight":1}]'
    )
    import importlib
    import config
    importlib.reload(config)

    results = Counter()
    n = 10000
    for _ in range(n):
        t = config.select_target("hard")
        results[t["model_id"]] += 1

    total = results["x"] + results["y"]
    pct_x = results["x"] / total * 100
    assert 70 < pct_x < 80, f"Expected ~75%, got {pct_x:.1f}%"

    del os.environ["TIER_HARD_CONFIG"]
    importlib.reload(config)
