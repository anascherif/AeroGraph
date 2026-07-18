"""Regression tests for the visual_search parameter-name mismatch
and the LLM failure -> 503 propagation path.

These cover bugs introduced in the pipeline code (not Nemotron's CORS/API
work) where:

1. ``keyframe_index.search_by_text`` accepted ``location_filter=`` but the
   callers (``api/query.py``, ``query_engine.py``) passed ``location_name=``.
   Result: TypeError on every visual_search call that included a location.
2. ``llm_client.ask()`` returned a soft apology string on request failures,
   causing the API layer's 503 branch (which only catches RuntimeError) to
   never fire — clients saw 200 with "Sorry, I couldn't process that right
   now." instead of an explicit 503.
"""

from __future__ import annotations

import inspect

from backend.pipeline.keyframe_index import KeyframeIndex
from backend.pipeline import llm_client


def test_search_by_text_accepts_location_name() -> None:
    """search_by_text must accept location_name= (not location_filter=)."""
    sig = inspect.signature(KeyframeIndex.search_by_text)
    params = set(sig.parameters.keys())
    assert "location_name" in params, (
        f"search_by_text must accept location_name=. Got params: {params}"
    )
    assert "location_filter" not in params, (
        "search_by_text should NOT use the old location_filter name — "
        "it was inconsistent with the rest of the codebase and caused "
        "TypeError in callers."
    )
    print("test_search_by_text_accepts_location_name PASSED")


def test_llm_ask_propagates_runtime_error_on_request_failure(monkeypatch=None) -> None:
    """llm_client.ask() must raise RuntimeError when the upstream API call
    fails, so the API layer can convert it into HTTP 503 instead of silently
    returning 200 with an apology string.
    """
    # Bypass _get_client() — we don't need a real OpenAI client, we just need
    # the inner create() call to blow up.
    class _FakeChat:
        def __call__(self, *a, **kw):
            raise RuntimeError("simulated network failure")

    class _FakeCompletions:
        def __init__(self):
            self.create = _FakeChat()

    class _FakeChatNamespace:
        def __init__(self):
            self.completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self):
            self.chat = _FakeChatNamespace()

    # Inject the fake client as if it were already initialised.
    original = llm_client._client
    llm_client._client = _FakeClient()
    try:
        raised = False
        try:
            llm_client.ask("where are my keys?", context="stub")
        except RuntimeError:
            raised = True
        assert raised, (
            "llm_client.ask() must raise RuntimeError on upstream failure "
            "so the API layer can return 503. It currently returned a soft "
            "apology string, causing a misleading 200 response."
        )
    finally:
        llm_client._client = original

    print("test_llm_ask_propagates_runtime_error_on_request_failure PASSED")


if __name__ == "__main__":
    test_search_by_text_accepts_location_name()
    test_llm_ask_propagates_runtime_error_on_request_failure()
    print()
    print("ALL PIPELINE BUGFIX REGRESSION TESTS PASSED")
