import pytest

import backend.accounts as accounts_module
import backend.risk as risk_module


@pytest.fixture
def env(monkeypatch):
    """Isolate Account from the real database and market: prices come from a
    dict, accounts live in memory, and log lines are collected in a list."""
    store: dict[str, dict] = {}
    logs: list[tuple[str, str, str]] = []
    prices = {"AAPL": 100.0, "MSFT": 100.0}

    def get_price(symbol: str) -> float:
        return prices.get(symbol.upper(), 0.0)

    def log(name, type, message):
        logs.append((name, type, message))

    monkeypatch.setattr(accounts_module, "get_share_price", get_price)
    monkeypatch.setattr(risk_module, "get_share_price", get_price)
    monkeypatch.setattr(accounts_module, "read_account", lambda name: store.get(name.lower()))
    monkeypatch.setattr(
        accounts_module, "write_account", lambda name, fields: store.__setitem__(name.lower(), fields)
    )
    monkeypatch.setattr(accounts_module, "write_log", log)
    monkeypatch.setattr(risk_module, "write_log", log)
    return {"prices": prices, "store": store, "logs": logs}
