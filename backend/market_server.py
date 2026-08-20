"""A thin MCP market data server for the trader.

Massive's own MCP server exposes a generic call_api tool over the whole REST
surface, and agents kept picking endpoints the free plan rejects (HTTP 403) or
bursting through its 5 requests/minute limit. This server offers only what a
trader needs and routes it through the shared price cache in market.py, so the
price an agent sees is the price its trade will execute at.
"""

from mcp.server.fastmcp import FastMCP

from .market import get_share_price, is_market_open

mcp = FastMCP("market_server")


@mcp.tool()
async def lookup_share_price(symbol: str) -> float:
    """Current share price for the given stock symbol (previous close when the market is closed)."""
    return get_share_price(symbol)


@mcp.tool()
async def market_is_open() -> bool:
    """Whether the US stock market is currently open for trading."""
    return is_market_open()


if __name__ == "__main__":
    mcp.run(transport="stdio")
