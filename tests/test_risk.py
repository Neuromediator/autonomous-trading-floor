import pytest

from backend.accounts import Account


def test_buy_within_concentration_limit_passes(env):
    account = Account.get("testy")
    # 29 shares at ~$100.2 is just under 30% of the $10k portfolio
    account.buy_shares("AAPL", 29, "sized within limits")
    assert account.holdings == {"AAPL": 29}


def test_buy_over_concentration_limit_rejected(env):
    account = Account.get("testy")
    with pytest.raises(ValueError, match="risk limits"):
        account.buy_shares("AAPL", 40, "oversized position")
    assert account.holdings == {}
    assert any("Risk check rejected" in message for _, _, message in env["logs"])


def test_short_over_concentration_limit_rejected(env):
    account = Account.get("testy")
    with pytest.raises(ValueError, match="risk limits"):
        account.sell_shares("AAPL", 40, "oversized short")
    assert account.holdings == {}


def test_total_short_exposure_limit(env):
    account = Account.get("testy")
    # Each short alone respects the 30% concentration limit...
    account.sell_shares("AAPL", 28, "first short")
    # ...but together they would breach the 50% total short exposure limit
    with pytest.raises(ValueError, match="short exposure"):
        account.sell_shares("MSFT", 28, "second short")
    assert account.holdings == {"AAPL": -28}
