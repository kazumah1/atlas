from datetime import datetime

import numpy as np

from apps.api import helpers


def _paper(title: str, paper_id: str = "paper-id"):
    return {
        "id": paper_id,
        "title": title,
        "abstract": None,
        "summary": None,
        "tags": None,
        "published_at": datetime.today(),
    }


def test_title_search_works_without_embedding_configuration(monkeypatch):
    result = _paper("Convergence of Power Matrices")
    received = {}

    def text_search(query, **kwargs):
        received["query"] = query
        return [result]

    monkeypatch.setattr(helpers, "db_keyword_search", text_search)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setattr(
        helpers,
        "embed_query",
        lambda _query: (_ for _ in ()).throw(AssertionError("embedding should be skipped")),
    )

    ids = helpers.get_sorted_results(
        "convergence of power matrices", None, None, None
    )

    assert received["query"] == "convergence of power matrices"
    assert ids == ["paper-id"]


def test_title_search_survives_embedding_failure(monkeypatch):
    result = _paper("Convergence of Power Matrices")
    monkeypatch.setenv("OPENAI_API_KEY", "configured-but-unavailable")
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setattr(helpers, "db_keyword_search", lambda *_args, **_kwargs: [result])
    monkeypatch.setattr(
        helpers,
        "embed_query",
        lambda _query: (_ for _ in ()).throw(RuntimeError("embedding service unavailable")),
    )

    ids = helpers.get_sorted_results(
        "convergence of power matrices", None, None, None
    )

    assert ids == ["paper-id"]


def test_exact_title_ranks_above_semantic_only_match(monkeypatch):
    exact = _paper("Convergence of Power Matrices", "exact")
    semantic = _paper("Unrelated Paper", "semantic")
    semantic["embedding"] = np.array([1.0, 0.0], dtype=np.float32)

    monkeypatch.setenv("OPENAI_API_KEY", "configured")
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setattr(helpers, "db_keyword_search", lambda *_args, **_kwargs: [exact])
    monkeypatch.setattr(
        helpers,
        "embed_query",
        lambda _query: np.array([1.0, 0.0], dtype=np.float32),
    )
    monkeypatch.setattr(helpers, "db_semantic_search", lambda _embeddings: [semantic])

    ids = helpers.get_sorted_results(
        "convergence of power matrices", None, None, None
    )

    assert ids == ["exact", "semantic"]
