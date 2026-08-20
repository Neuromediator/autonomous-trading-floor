"""A thin MCP web search server for the researcher.

Tavily's own MCP server lets the caller choose max_results (up to 20) and
include_raw_content, and the researcher kept asking for both: a single search
then returns ~30k tokens, several run in parallel each turn, and the results
accumulate across turns until the request exceeds the model's token limit.
This server exposes one search tool whose breadth and payload are fixed here
rather than chosen by the model.

Two more limits protect the search plan's credits, which are metered per call:
responses are cached in the shared database, since four traders in one round
ask near-identical questions, and each run gets a fixed budget of live
searches. One server process serves one trader's run, so the budget is
per-run simply by being a module-level counter.
"""

import os
import time

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .database import read_search, write_search

load_dotenv(override=True)

tavily_api_key = os.getenv("TAVILY_API_KEY")

SEARCH_URL = "https://api.tavily.com/search"
MAX_RESULTS = 4
# Roughly 375 tokens per result, so a full search costs about 1.5k tokens.
MAX_CONTENT_CHARS = 1500
TIMEOUT_SECONDS = 30
# Four traders a day at this budget stay inside the 1000 credits a month the
# free plan allows, before the cache saves any of them.
MAX_SEARCHES_PER_RUN = int(os.getenv("MAX_SEARCHES_PER_RUN", "10"))
# Long enough to collapse one round's duplicates, short enough that a trader
# never acts on yesterday's news.
SEARCH_CACHE_TTL_SECONDS = int(os.getenv("SEARCH_CACHE_TTL_SECONDS", str(6 * 3600)))

searches_spent = 0

mcp = FastMCP("research_server")


def normalise(query: str) -> str:
    """Cache key: casing and spacing shouldn't cost a second credit."""
    return " ".join(query.lower().split())


async def fetch_search(query: str) -> str:
    """Ask Tavily, and format the answer compactly."""
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {tavily_api_key}"},
            json={
                "query": query,
                "max_results": MAX_RESULTS,
                "search_depth": "basic",
                "include_answer": True,
                "include_raw_content": False,
            },
        )
        response.raise_for_status()
        payload = response.json()

    lines = []
    answer = payload.get("answer")
    if answer:
        lines.append(f"Summary: {answer}")
    for result in payload.get("results", []):
        content = (result.get("content") or "").strip()[:MAX_CONTENT_CHARS]
        lines.append(f"\n{result.get('title', 'Untitled')} — {result.get('url', '')}\n{content}")
    return "\n".join(lines) if lines else f"No results for {query!r}"


async def run_search(query: str) -> str:
    """A fresh cached answer, else a live search while the run's budget lasts."""
    global searches_spent
    if not tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is not set; web search is unavailable")

    key = normalise(query)
    cached = read_search(key)
    if cached and time.time() - cached[1] < SEARCH_CACHE_TTL_SECONDS:
        return cached[0]

    if searches_spent >= MAX_SEARCHES_PER_RUN:
        # A stale answer still beats none; otherwise say so plainly, so the
        # agent reasons with what it has instead of retrying.
        if cached:
            return cached[0]
        return (
            "This run's search budget is spent. Draw conclusions from what you "
            "already found and from your memory instead of searching again."
        )

    searches_spent += 1
    response = await fetch_search(key)
    write_search(key, response, time.time())
    return response


@mcp.tool()
async def search_web(query: str) -> str:
    """Search the web for recent information. Returns a short summary and the top results."""
    return await run_search(query)


if __name__ == "__main__":
    mcp.run(transport="stdio")
