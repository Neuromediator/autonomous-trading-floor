"""Hard risk limits enforced on every trade.

The RiskManager agent advises the traders before they act, but these checks are
the real guardrails: Account.buy_shares and sell_shares run them before
executing, and a rejected trade surfaces as a tool error the agent can read
and adapt to.
"""

from .market import get_share_price
from .database import write_log

# A single position's market value may not exceed this share of portfolio value.
MAX_POSITION_CONCENTRATION = 0.30
# Total short market value may not exceed this share of portfolio value.
MAX_SHORT_EXPOSURE = 0.50


def _reject(account, reason: str):
    write_log(account.name, "account", f"Risk check rejected a trade: {reason}")
    raise ValueError(f"Trade rejected by risk limits: {reason}")


def check_trade(account, symbol: str, quantity_delta: int, price: float):
    """Validate the trade that would change `symbol` by `quantity_delta` shares.

    Positive delta is a buy, negative a sell. Raises ValueError if the resulting
    position would break a limit.
    """
    portfolio_value = account.calculate_portfolio_value()
    new_quantity = account.holdings.get(symbol, 0) + quantity_delta

    position_value = abs(new_quantity) * price
    max_position = MAX_POSITION_CONCENTRATION * portfolio_value
    if position_value > max_position:
        _reject(
            account,
            f"{symbol} position of {abs(new_quantity)} shares (${position_value:,.2f}) would exceed "
            f"{MAX_POSITION_CONCENTRATION:.0%} of the ${portfolio_value:,.2f} portfolio. "
            f"Keep the position at or below ${max_position:,.2f}.",
        )

    if new_quantity < 0:
        holdings_after = dict(account.holdings)
        holdings_after[symbol] = new_quantity
        short_exposure = sum(
            abs(quantity) * (price if held == symbol else get_share_price(held))
            for held, quantity in holdings_after.items()
            if quantity < 0
        )
        max_short = MAX_SHORT_EXPOSURE * portfolio_value
        if short_exposure > max_short:
            _reject(
                account,
                f"total short exposure of ${short_exposure:,.2f} would exceed "
                f"{MAX_SHORT_EXPOSURE:.0%} of the ${portfolio_value:,.2f} portfolio. "
                f"Keep total shorts at or below ${max_short:,.2f}.",
            )
