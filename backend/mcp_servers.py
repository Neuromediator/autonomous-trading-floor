import os
from pathlib import Path
from dotenv import load_dotenv
from agents.mcp import MCPServerStdio, create_static_tool_filter
from .market import massive_api_key

load_dotenv(override=True)

PROJECT_DIR = str(Path(__file__).resolve().parent.parent)
TIMEOUT = 120

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
    params = [
        {"command": "uv", "args": ["run", "-m", "backend.accounts_server"], "cwd": PROJECT_DIR},
        {"command": "uv", "args": ["run", "-m", "backend.push_server"], "cwd": PROJECT_DIR},
        {"command": "uv", "args": ["run", "-m", "backend.market_server"], "cwd": PROJECT_DIR},
    ]
    return [MCPServerStdio(p, client_session_timeout_seconds=TIMEOUT) for p in params]


def risk_manager_mcp_servers() -> list[MCPServerStdio]:
    """A read-only view of the Accounts server for the risk manager.

    The risk manager must be able to inspect balances and holdings but never
    trade or change strategies, so the server is filtered to its read tools.
    """
    params = {"command": "uv", "args": ["run", "-m", "backend.accounts_server"], "cwd": PROJECT_DIR}
    return [
        MCPServerStdio(
            params,
            client_session_timeout_seconds=TIMEOUT,
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
    fetch = MCPServerStdio(
        {"command": "uvx", "args": ["--with", "mcp<2","mcp-server-fetch"]},
        client_session_timeout_seconds=TIMEOUT,
    )
    search = MCPServerStdio(
        {"command": "uv", "args": ["run", "-m", "backend.research_server"], "cwd": PROJECT_DIR},
        client_session_timeout_seconds=TIMEOUT,
    )
    memory = MCPServerStdio(
        {
            "command": "uvx",
            "args": ["mcp-server-qdrant"],
            "env": {
                "QDRANT_LOCAL_PATH": f"{PROJECT_DIR}/memory/qdrant_{name.lower()}",
                "COLLECTION_NAME": f"{name.lower()}-memories",
            },
        },
        client_session_timeout_seconds=TIMEOUT,
    )
    return [fetch, search, memory]
