import os
import shutil
from pathlib import Path
from dotenv import load_dotenv
from agents.mcp import MCPServerStdio, create_static_tool_filter
from .market import massive_api_key

load_dotenv(override=True)

PROJECT_DIR = str(Path(__file__).resolve().parent.parent)
TIMEOUT = 120
# The third-party MCP servers, and the command that installs each one.
THIRD_PARTY_SERVERS = {
    "mcp-server-fetch": "uv tool install --with 'mcp<2' mcp-server-fetch",
    "mcp-server-qdrant": "uv tool install mcp-server-qdrant",
}


def installed(command: str) -> str:
    """The command for a third-party server, checked before a round leans on it.

    These are installed, not run through uvx. uvx re-resolves the dependency
    tree on every launch, so any release anywhere in it makes uv build a fresh
    environment mid-round — and a fresh readabilipy has no node_modules, runs
    "npm install" on first use, and writes npm's output to stdout, which for a
    stdio MCP server is the JSON-RPC channel itself. It happened on 25 Aug 2026.
    "uv tool install" pins one environment uv will not rebuild, so an install
    like that happens once, at setup time, where its output is harmless.
    A missing command is a setup mistake, so say so here rather than let the
    trader hit an opaque failure in the middle of a round.
    """
    if shutil.which(command) is None:
        raise RuntimeError(f"{command} is not installed. Run: {THIRD_PARTY_SERVERS[command]}")
    return command


def server(name: str, params: dict, **kwargs) -> MCPServerStdio:
    """One stdio MCP server, named and with its tool list cached.

    The name is what the trace shows; without it every server reports the
    command that launched it, and ours all launch with "uv". Caching the tool
    list matters as much: the SDK otherwise re-lists tools on every turn, which
    costs a round trip per server per turn and buries the activity log under
    identical entries. No server here gains or loses tools mid-run.
    """
    return MCPServerStdio(
        params,
        name=name,
        cache_tools_list=True,
        client_session_timeout_seconds=TIMEOUT,
        **kwargs,
    )


def trader_mcp_servers() -> list[MCPServerStdio]:
    """The trader's MCP servers: our Accounts, Push Notification and Market data servers.

    Market data is our own thin server over the shared price cache rather than
    Massive's generic call_api server: the free plan rejects many endpoints
    (HTTP 403) and allows 5 requests/minute, so agents exploring the raw API
    wasted quota and turns. This way the price a trader sees is the price its
    trade executes at.
    """
    if not massive_api_key:
        raise RuntimeError("MASSIVE_API_KEY is not set; live market data is required to trade")
    return [
        server("accounts", {"command": "uv", "args": ["run", "-m", "backend.accounts_server"], "cwd": PROJECT_DIR}),
        server("push", {"command": "uv", "args": ["run", "-m", "backend.push_server"], "cwd": PROJECT_DIR}),
        server("market", {"command": "uv", "args": ["run", "-m", "backend.market_server"], "cwd": PROJECT_DIR}),
    ]


def risk_manager_mcp_servers() -> list[MCPServerStdio]:
    """A read-only view of the Accounts server for the risk manager.

    The risk manager must be able to inspect balances and holdings but never
    trade or change strategies, so the server is filtered to its read tools.
    """
    return [
        server(
            "accounts (read-only)",
            {"command": "uv", "args": ["run", "-m", "backend.accounts_server"], "cwd": PROJECT_DIR},
            tool_filter=create_static_tool_filter(allowed_tool_names=["get_balance", "get_holdings"]),
        )
    ]


def researcher_mcp_servers(name: str) -> list[MCPServerStdio]:
    """The researcher's MCP servers: Fetch, web search and Qdrant memory.

    Search is our own server over Tavily rather than Tavily's, which let the
    model ask for 20 results with raw page content — about 30k tokens a call,
    several calls a turn, accumulating until the request blew past the model's
    token limit. Ours fixes the breadth and truncates each result.
    Memory is a per-trader Qdrant collection run in local mode (no server needed);
    fastembed downloads its embedding model on first use.
    """
    fetch = server("fetch", {"command": installed("mcp-server-fetch"), "args": []})
    search = server(
        "search",
        {"command": "uv", "args": ["run", "-m", "backend.research_server"], "cwd": PROJECT_DIR},
    )
    memory = server(
        f"memory ({name.lower()})",
        {
            "command": installed("mcp-server-qdrant"),
            "args": [],
            "env": {
                "QDRANT_LOCAL_PATH": f"{PROJECT_DIR}/memory/qdrant_{name.lower()}",
                "COLLECTION_NAME": f"{name.lower()}-memories",
            },
        },
    )
    return [fetch, search, memory]
