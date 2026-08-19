"""Share prices from the Massive market data API, with a shared SQLite cache.

MASSIVE_API_KEY is required: there is no simulated fallback, so a portfolio can
never mix real and synthetic prices. Prices are cached in the accounts database,
shared by every process (the engine, each trader's accounts server, the API).
A fresh cache hit is served without an API call; when Massive is unavailable
the last known price is used however old it is; a symbol never priced before
raises, so a trade fails loudly instead of executing at a made-up price.
"""

import os
import time
from dotenv import load_dotenv
from massive import RESTClient
from .database import read_price, write_price

load_dotenv(override=True)

massive_api_key = os.getenv("MASSIVE_API_KEY")

CACHE_TTL_SECONDS = 120


def _last_trade(client: RESTClient, symbol: str) -> float:
    return float(client.get_last_trade(symbol).price)


def _snapshot(client: RESTClient, symbol: str) -> float:
    snapshot = client.get_snapshot_ticker("stocks", symbol)
    return float(snapshot.min.close or snapshot.prev_day.close)


def _previous_close(client: RESTClient, symbol: str) -> float:
    return float(client.get_previous_close_agg(symbol)[0].close)


# Best price first, prior close last. Lower tier plans reject the earlier calls,
# so we remember the first tier that works and start there next time.
price_methods = [_last_trade, _snapshot, _previous_close]
plan_tier = 0


def get_share_price(symbol: str) -> float:
    """Return the current price for a symbol.

    Served from the shared cache when fresh; otherwise fetched from Massive and
    cached. If Massive fails, the last known price wins over failing the caller;
    only a symbol with no price history at all raises.
    """
    if not massive_api_key:
        raise RuntimeError("MASSIVE_API_KEY is not set; live market data is required")
    symbol = symbol.upper()
    cached = read_price(symbol)
    if cached and time.time() - cached[1] < CACHE_TTL_SECONDS:
        return cached[0]
    try:
        price = get_share_price_massive(symbol)
        write_price(symbol, price, time.time())
        return price
    except Exception as e:
        if cached:
            print(f"Massive API unavailable ({e}); using the last known price for {symbol}")
            return cached[0]
        raise RuntimeError(
            f"No price available for {symbol}: the market data API is unavailable "
            f"and no earlier price is cached. Try again shortly. ({e})"
        ) from None


def get_share_price_massive(symbol: str) -> float:
    """Best price the plan allows, remembering the working tier to avoid repeat failures."""
    global plan_tier
    client = RESTClient(massive_api_key)
    for tier in range(plan_tier, len(price_methods)):
        try:
            price = price_methods[tier](client, symbol)
            plan_tier = tier
            return price
        except Exception:
            continue
    raise RuntimeError(f"No Massive price available for {symbol}")


def is_market_open() -> bool:
    """Whether the US market is open; True if Massive is unreachable."""
    if not massive_api_key:
        return True
    try:
        client = RESTClient(massive_api_key)
        return client.get_market_status().market == "open"
    except Exception:
        return True
