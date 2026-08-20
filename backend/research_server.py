"""A thin MCP web search server for the researcher.

Tavily's own MCP server lets the caller choose max_results (up to 20) and
include_raw_content, and the researcher kept asking for both: a single search
then returns ~30k tokens, several run in parallel each turn, and the results
accumulate across turns until the request exceeds the model's token limit.
This server exposes one search tool whose breadth and payload are fixed here
rather than chosen by the model.
"""

import os

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(override=True)

tavily_api_key = os.getenv("TAVILY_API_KEY")

SEARCH_URL = "https://api.tavily.com/search"
MAX_RESULTS = 4
# Roughly 375 tokens per result, so a full search costs about 1.5k tokens.
MAX_CONTENT_CHARS = 1500
TIMEOUT_SECONDS = 30

mcp = FastMCP("research_server")


@mcp.tool()
async def search_web(query: str) -> str:
    """Search the web for recent information. Returns a short summary and the top results."""
    if not tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is not set; web search is unavailable")
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


if __name__ == "__main__":
    mcp.run(transport="stdio")
