import pytest

from backend.accounts import Account, INITIAL_BALANCE, SPREAD


def test_buy_and_sell_round_trip(env):
    account = Account.get("testy")
    account.buy_shares("AAPL", 10, "test buy")
    assert account.holdings == {"AAPL": 10}
    assert account.balance == pytest.approx(INITIAL_BALANCE - 10 * 100.0 * (1 + SPREAD))

    account.sell_shares("AAPL", 10, "test sell")
    assert account.holdings == {}
    assert account.balance == pytest.approx(
        INITIAL_BALANCE - 10 * 100.0 * (1 + SPREAD) + 10 * 100.0 * (1 - SPREAD)
    )
    assert len(account.transactions) == 2
    assert account.transactions[1].quantity == -10


def test_insufficient_funds(env):
    account = Account.get("testy")
    with pytest.raises(ValueError, match="Insufficient funds"):
        account.buy_shares("AAPL", 200, "too big")


def test_unrecognized_symbol(env):
    account = Account.get("testy")
    with pytest.raises(ValueError, match="Unrecognized symbol"):
        account.buy_shares("NOPE", 1, "bad ticker")
    with pytest.raises(ValueError, match="Unrecognized symbol"):
        account.sell_shares("NOPE", 1, "bad ticker")


def test_short_open_and_cover(env):
    account = Account.get("testy")
    account.sell_shares("AAPL", 10, "open short")
    assert account.holdings == {"AAPL": -10}
    assert account.balance == pytest.approx(INITIAL_BALANCE + 10 * 100.0 * (1 - SPREAD))

    account.buy_shares("AAPL", 10, "cover short")
    assert account.holdings == {}
    # A full short round trip costs twice the spread
    assert account.balance == pytest.approx(INITIAL_BALANCE - 2 * 10 * 100.0 * SPREAD)


def test_short_profits_when_price_falls(env):
    account = Account.get("testy")
    account.sell_shares("AAPL", 10, "open short")
    value_at_open = account.calculate_portfolio_value()

    env["prices"]["AAPL"] = 90.0
    value_after_fall = account.calculate_portfolio_value()
    assert value_after_fall == pytest.approx(value_at_open + 10 * 10.0)


def test_portfolio_value_with_signed_holdings(env):
    account = Account.get("testy")
    account.buy_shares("AAPL", 5, "long")
    account.sell_shares("MSFT", 5, "short")
    expected = account.balance + 5 * 100.0 - 5 * 100.0
    assert account.calculate_portfolio_value() == pytest.approx(expected)
