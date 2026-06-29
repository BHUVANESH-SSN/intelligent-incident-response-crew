import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_vector_store_unavailable():
    from src.integrations.vector_store import VectorStoreClient
    vs = object.__new__(VectorStoreClient)
    vs._available = False
    return vs


def test_vector_store_search_returns_empty_when_unavailable():
    vs = _make_vector_store_unavailable()
    assert vs.search("memory leak") == []


def test_search_runbooks_falls_back_to_keywords_when_vector_empty():
    """When vector store returns [], keyword search is used instead."""
    with patch("src.tools.vector_store_client") as mock_vs:
        mock_vs.search.return_value = []
        from src.tools import search_runbooks
        result_str = search_runbooks.func("memory leak out of memory heap")
    result = json.loads(result_str)
    assert isinstance(result, list)
    assert len(result) >= 1
    titles = [r.get("title", "") for r in result]
    assert any("emory" in t for t in titles)  # "Memory" case-insensitive


def test_search_runbooks_uses_vector_results_when_available():
    """When vector store returns results, they are passed through directly."""
    vector_hit = [{"title": "Vector-found Runbook", "steps": ["step 1"], "score": 0.95}]
    with patch("src.tools.vector_store_client") as mock_vs:
        mock_vs.search.return_value = vector_hit
        from src.tools import search_runbooks
        result_str = search_runbooks.func("anything")
    assert json.loads(result_str) == vector_hit


def test_runbooks_constant_is_exported():
    from src.tools import RUNBOOKS
    assert isinstance(RUNBOOKS, dict)
    assert len(RUNBOOKS) >= 5
    assert "high_memory_usage" in RUNBOOKS
    rb = RUNBOOKS["high_memory_usage"]
    assert "title" in rb
    assert "keywords" in rb
    assert "steps" in rb
