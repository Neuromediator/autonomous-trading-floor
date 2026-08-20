import time

import pytest

import backend.research_server as research


@pytest.fixture
def search_store(monkeypatch):
    """In-memory stand-in for the shared SQLite search cache."""
    store: dict[str, tuple[str, float]] = {}
    monkeypatch.setattr(research, "read_search", store.get)
    monkeypatch.setattr(research, "write_search", lambda q, r, t: store.__setitem__(q, (r, t)))
    monkeypatch.setattr(research, "tavily_api_key", "test-key")
    monkeypatch.setattr(research, "searches_spent", 0)
    return store


@pytest.fixture
def calls(monkeypatch):
    """Record live searches instead of making them."""
    made: list[str] = []

    async def fake_fetch(query: str) -> str:
        made.append(query)
        return f"results for {query}"

    monkeypatch.setattr(research, "fetch_search", fake_fetch)
    return made


async def test_repeat_query_is_served_from_cache(search_store, calls):
    assert await research.run_search("Gold ETF outlook") == "results for gold etf outlook"
    # Different casing and spacing, same question.
    assert await research.run_search("  gold   ETF Outlook ") == "results for gold etf outlook"
    assert calls == ["gold etf outlook"]


async def test_expired_cache_searches_again(search_store, calls):
    search_store["gold"] = ("old news", time.time() - research.SEARCH_CACHE_TTL_SECONDS - 1)
    assert await research.run_search("gold") == "results for gold"
    assert calls == ["gold"]


async def test_budget_limits_live_searches(search_store, calls, monkeypatch):
    monkeypatch.setattr(research, "MAX_SEARCHES_PER_RUN", 2)
    for i in range(4):
        await research.run_search(f"query {i}")
    assert calls == ["query 0", "query 1"]


async def test_exhausted_budget_says_so(search_store, calls, monkeypatch):
    monkeypatch.setattr(research, "MAX_SEARCHES_PER_RUN", 0)
    assert "budget is spent" in await research.run_search("anything")


async def test_exhausted_budget_still_serves_a_stale_answer(search_store, calls, monkeypatch):
    monkeypatch.setattr(research, "MAX_SEARCHES_PER_RUN", 0)
    search_store["gold"] = ("old news", time.time() - research.SEARCH_CACHE_TTL_SECONDS - 1)
    assert await research.run_search("gold") == "old news"


async def test_cached_hits_do_not_spend_budget(search_store, calls, monkeypatch):
    monkeypatch.setattr(research, "MAX_SEARCHES_PER_RUN", 1)
    await research.run_search("gold")
    for _ in range(3):
        assert await research.run_search("gold") == "results for gold"
    assert calls == ["gold"]
