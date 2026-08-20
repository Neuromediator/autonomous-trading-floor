import time

import pytest

import backend.market as market


@pytest.fixture
def price_store(monkeypatch):
    """In-memory stand-in for the shared SQLite price cache."""
    store: dict[str, tuple[float, float]] = {}
    monkeypatch.setattr(market, "read_price", store.get)
    monkeypatch.setattr(market, "write_price", lambda s, p, t: store.__setitem__(s, (p, t)))
    monkeypatch.setattr(market, "massive_api_key", "test-key")
    return store


def test_cache_avoids_repeat_calls(price_store, monkeypatch):
    calls = []
    monkeypatch.setattr(market, "get_share_price_massive", lambda s: calls.append(s) or 100.0)

    assert market.get_share_price("aapl") == 100.0
    assert market.get_share_price("AAPL") == 100.0
    assert calls == ["AAPL"]


def test_expired_cache_refreshes(price_store, monkeypatch):
    price_store["AAPL"] = (100.0, time.time() - market.CACHE_TTL_SECONDS - 1)
    monkeypatch.setattr(market, "get_share_price_massive", lambda s: 110.0)
    assert market.get_share_price("AAPL") == 110.0
    assert price_store["AAPL"][0] == 110.0


def test_stale_price_preferred_over_failure(price_store, monkeypatch):
    price_store["AAPL"] = (100.0, time.time() - market.CACHE_TTL_SECONDS - 1)

    def down(symbol):
        raise RuntimeError("Massive is down")

    monkeypatch.setattr(market, "get_share_price_massive", down)
    assert market.get_share_price("AAPL") == 100.0


def test_unknown_symbol_raises_instead_of_inventing_a_price(price_store, monkeypatch):
    def down(symbol):
        raise RuntimeError("Massive is down")

    monkeypatch.setattr(market, "get_share_price_massive", down)
    with pytest.raises(RuntimeError, match="No price available"):
        market.get_share_price("AAPL")


def test_rate_limit_is_retried_until_a_price_arrives(price_store, monkeypatch):
    sleeps = []
    monkeypatch.setattr(market.time, "sleep", sleeps.append)
    attempts = []

    def flaky(symbol):
        attempts.append(symbol)
        if len(attempts) < 2:
            raise RuntimeError("HTTP 429 Too Many Requests")
        return 100.0

    monkeypatch.setattr(market, "get_share_price_massive", flaky)
    assert market.get_share_price("AAPL") == 100.0
    assert sleeps == [market.RATE_LIMIT_WAITS_SECONDS[0]]
    assert price_store["AAPL"][0] == 100.0


def test_rate_limit_gives_up_after_all_waits(price_store, monkeypatch):
    sleeps = []
    monkeypatch.setattr(market.time, "sleep", sleeps.append)

    def limited(symbol):
        raise RuntimeError("HTTP 429 Too Many Requests")

    monkeypatch.setattr(market, "get_share_price_massive", limited)
    with pytest.raises(RuntimeError, match="No price available"):
        market.get_share_price("AAPL")
    assert sleeps == market.RATE_LIMIT_WAITS_SECONDS


def test_non_rate_limit_error_is_not_retried(price_store, monkeypatch):
    sleeps = []
    monkeypatch.setattr(market.time, "sleep", sleeps.append)

    def down(symbol):
        raise RuntimeError("Massive is down")

    monkeypatch.setattr(market, "get_share_price_massive", down)
    with pytest.raises(RuntimeError, match="No price available"):
        market.get_share_price("AAPL")
    assert sleeps == []


def test_cached_price_never_spends_quota(price_store, monkeypatch):
    price_store["AAPL"] = (100.0, time.time() - 999999)

    def explode(symbol):
        raise AssertionError("the API must not be called for a cached symbol")

    monkeypatch.setattr(market, "get_share_price_massive", explode)
    assert market.get_cached_share_price("AAPL") == 100.0


def test_cached_price_falls_back_to_live_fetch_for_unknown_symbol(price_store, monkeypatch):
    monkeypatch.setattr(market, "get_share_price_massive", lambda s: 42.0)
    assert market.get_cached_share_price("MSFT") == 42.0


def test_missing_key_raises(price_store, monkeypatch):
    monkeypatch.setattr(market, "massive_api_key", None)
    with pytest.raises(RuntimeError, match="MASSIVE_API_KEY"):
        market.get_share_price("AAPL")
