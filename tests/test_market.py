import time

import backend.market as market


def setup_function():
    market._price_cache.clear()


def test_cache_avoids_repeat_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(market, "massive_api_key", "test-key")
    monkeypatch.setattr(market, "get_share_price_massive", lambda s: calls.append(s) or 100.0)

    assert market.get_share_price("aapl") == 100.0
    assert market.get_share_price("AAPL") == 100.0
    assert calls == ["AAPL"]


def test_expired_cache_refreshes(monkeypatch):
    monkeypatch.setattr(market, "massive_api_key", "test-key")
    monkeypatch.setattr(market, "get_share_price_massive", lambda s: 100.0)
    market.get_share_price("AAPL")

    market._price_cache["AAPL"] = (100.0, time.time() - market.CACHE_TTL_SECONDS - 1)
    monkeypatch.setattr(market, "get_share_price_massive", lambda s: 110.0)
    assert market.get_share_price("AAPL") == 110.0


def test_stale_price_preferred_over_simulator(monkeypatch):
    monkeypatch.setattr(market, "massive_api_key", "test-key")
    monkeypatch.setattr(market, "get_share_price_massive", lambda s: 100.0)
    market.get_share_price("AAPL")

    market._price_cache["AAPL"] = (100.0, time.time() - market.CACHE_TTL_SECONDS - 1)

    def down(symbol):
        raise RuntimeError("Massive is down")

    monkeypatch.setattr(market, "get_share_price_massive", down)
    assert market.get_share_price("AAPL") == 100.0


def test_simulator_when_no_key(monkeypatch):
    monkeypatch.setattr(market, "massive_api_key", None)
    assert market.get_share_price("AAPL") > 0
