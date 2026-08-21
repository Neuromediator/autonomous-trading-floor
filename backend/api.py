"""HTTP API over the trading floor, for a separate frontend to consume.

The Gradio dashboard in demo/ reads accounts.db in-process. This serves the same
data as JSON so a decoupled web frontend can render it. Everything here is
read-only; the trading floor writes the database out of band.

Run it from the 6_mcp directory so it shares the engine's accounts.db:

    uv run uvicorn backend.api:app --port 8000
"""

from fastapi import FastAPI, HTTPException

from backend import market
from backend.accounts import Account
from backend.database import read_log, read_strategies
from backend.risk import MAX_SHORT_EXPOSURE
from backend.templates import persona
from backend.trading_floor import names, lastnames, short_model_names

# Mirrors the log colours in demo/ so the frontend reproduces the same panel.
LOG_COLORS = {
    "trace": "#87CEEB",
    "agent": "#00dddd",
    "function": "#00dd00",
    "generation": "#dddd00",
    "response": "#aa00dd",
    "account": "#dd0000",
}
DEFAULT_LOG_COLOR = "#87CEEB"

roster = [
    {"name": name, "lastname": lastname, "model_name": model_name}
    for name, lastname, model_name in zip(names, lastnames, short_model_names)
]
roster_by_name = {trader["name"].lower(): trader for trader in roster}

app = FastAPI(title="Trading Floor")


def average_cost(account: Account, symbol: str, quantity: int) -> float:
    """Average open price for this symbol's side: buys for a long, sells for a short."""
    is_long = quantity > 0
    same_side = [
        t for t in account.transactions if t.symbol == symbol and (t.quantity > 0) == is_long
    ]
    spend = sum(t.price * abs(t.quantity) for t in same_side)
    shares = sum(abs(t.quantity) for t in same_side)
    return spend / shares if shares else 0.0


def classify_trades(account: Account) -> list[dict]:
    """Every trade, labelled by what it did to the position.

    A negative quantity alone doesn't say whether the trader sold something it
    held or sold short, and once a short is covered nothing in the history shows
    it ever existed. Replaying the position per symbol recovers that: the label
    is the difference between reducing a long and opening a short.
    """
    position: dict[str, int] = {}
    trades = []
    for t in account.transactions:
        before = position.get(t.symbol, 0)
        after = before + t.quantity
        position[t.symbol] = after
        if t.quantity > 0:
            action = "COVER" if before < 0 else "BUY"
        else:
            action = "SHORT" if after < 0 else "SELL"
        trades.append({**t.model_dump(), "action": action})
    return trades


def short_exposure(account: Account, holdings: list[dict], portfolio_value: float) -> float:
    """Short market value as a share of the portfolio, against MAX_SHORT_EXPOSURE."""
    shorts = sum(-h["market_value"] for h in holdings if h["quantity"] < 0)
    return shorts / portfolio_value if portfolio_value > 0 else 0.0


def holdings_detail(account: Account) -> list[dict]:
    """Current holdings enriched with price, market value and unrealised profit."""
    details = []
    for symbol, quantity in account.holdings.items():
        price = market.get_cached_share_price(symbol)
        cost = average_cost(account, symbol, quantity)
        details.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "price": price,
                "avg_cost": cost,
                "market_value": price * quantity,
                "unrealized_pnl": (price - cost) * quantity,
            }
        )
    return details


def require_trader(name: str) -> dict:
    trader = roster_by_name.get(name.lower())
    if not trader:
        raise HTTPException(status_code=404, detail=f"Unknown trader {name}")
    return trader


@app.get("/api/traders")
def get_traders() -> list[dict]:
    """The four traders on the floor."""
    return roster


@app.get("/api/market")
def get_market() -> dict:
    """Which price source is live, and whether the market is open."""
    source = "massive" if market.massive_api_key else "offline"
    return {
        "source": source,
        "tier": market.price_tier_label(),
        "is_market_open": market.is_market_open(),
    }


@app.get("/api/traders/{name}")
def get_trader(name: str) -> dict:
    """A trader's full state: value, profit, holdings, transactions and history."""
    trader = require_trader(name)
    account = Account.get(name)
    holdings = holdings_detail(account)
    portfolio_value = account.balance + sum(h["market_value"] for h in holdings)
    return {
        "name": trader["name"],
        "lastname": trader["lastname"],
        "model_name": trader["model_name"],
        "balance": account.balance,
        "persona": persona(trader["name"]),
        "strategy": account.strategy,
        "strategy_revisions": len(read_strategies(name)),
        "portfolio_value": portfolio_value,
        "pnl": account.calculate_profit_loss(portfolio_value),
        "holdings": holdings,
        "transactions": classify_trades(account),
        "short_exposure": short_exposure(account, holdings, portfolio_value),
        "max_short_exposure": MAX_SHORT_EXPOSURE,
        "time_series": [{"datetime": ts, "value": value} for ts, value in account.portfolio_value_time_series],
    }


@app.get("/api/traders/{name}/logs")
def get_trader_logs(name: str, last_n: int = 13) -> list[dict]:
    """Recent trace and account log lines, oldest first, with their panel colour."""
    require_trader(name)
    rows = list(read_log(name, last_n))
    return [
        {"datetime": ts, "type": kind, "message": message, "color": LOG_COLORS.get(kind, DEFAULT_LOG_COLOR)}
        for ts, kind, message in rows
    ]


@app.get("/api/traders/{name}/strategies")
def get_trader_strategies(name: str) -> list[dict]:
    """Every strategy the trader has written, oldest first."""
    require_trader(name)
    return [{"datetime": ts, "strategy": strategy} for ts, strategy in read_strategies(name)]
