"""Tests for the search_runbooks keyword-scoring tool."""

import json

from src.tools import search_runbooks


def _run(symptom):
    fn = search_runbooks
    if hasattr(fn, "run"):
        out = fn.run(symptom=symptom)
    elif hasattr(fn, "func"):
        out = fn.func(symptom=symptom)
    else:
        out = fn(symptom=symptom)
    return json.loads(out)


def _keys(data):
    """Extract the 'key' field from each result item."""
    return [item.get("key", "") for item in data]


def test_memory_oom_matches_high_memory_usage():
    data = _run("memory oom heap")
    assert isinstance(data, list)
    assert data[0].get("key") == "high_memory_usage"


def test_5xx_error_spike_matches_high_error_rate():
    data = _run("5xx error spike")
    assert isinstance(data, list)
    assert "high_error_rate" in _keys(data)
    assert data[0].get("key") == "high_error_rate"


def test_disk_full_matches_disk_full():
    data = _run("disk full")
    assert isinstance(data, list)
    assert data[0].get("key") == "disk_full"


def test_nonsense_returns_no_match():
    data = _run("xyzzy quux flibberty")
    assert isinstance(data, list)
    assert len(data) == 1
    assert "message" in data[0]


def test_keywords_stripped_and_match_score_present():
    data = _run("memory")
    assert isinstance(data, list)
    runbook = data[0]
    assert "keywords" not in runbook
    assert "match_score" in runbook
    assert isinstance(runbook["match_score"], int)
    assert runbook["match_score"] > 0
