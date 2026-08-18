# Autonomous Trading Floor

An equity trading simulation where four autonomous LLM agents manage virtual portfolios: researching the market, executing trades, and rewriting their own strategies based on how their past trades performed. Built on the [Model Context Protocol](https://modelcontextprotocol.io/) and the OpenAI Agents SDK, with a FastAPI backend and a Vite/TypeScript dashboard.

> **Not a real trading tool.** This is a learning project about agentic AI architecture. Do not use it for actual trading decisions.

<!-- TODO: record the dashboard and drop the file in docs/dashboard.gif, then uncomment:
![Dashboard](docs/dashboard.gif)
-->

## How it works

Four traders — Warren (value), George (contrarian macro, shorts included), Ray (systematic), Cathie (crypto ETFs) — run on a timer. Each trader is an agent with its own MCP servers and two sub-agents wrapped as tools:

```
Trader agent
├── MCP: accounts   (buy, sell, balance, holdings, change_strategy)
├── MCP: push       (notifications)
├── MCP: market     (live prices via Massive, or a built-in simulator)
├── Tool: Researcher agent
│   ├── MCP: fetch          (read web pages)
│   ├── MCP: tavily         (web search, filtered to plain search)
│   └── MCP: qdrant         (per-trader semantic memory, local mode)
└── Tool: RiskManager agent
    └── MCP: accounts       (filtered to read-only tools)
```

Key mechanics:

- **Self-improving strategies.** Each trader's strategy is plain text stored with its account. The prompts ask the trader to review how its trades actually performed and rewrite the strategy accordingly — a real feedback loop from portfolio returns into future behavior.
- **Persistent memory.** The researcher stores findings in a per-trader Qdrant collection (local mode, fastembed embeddings) and recalls them before searching the web, building expertise across runs.
- **Short selling with guardrails.** Traders can open short positions. Hard risk limits are enforced in code on every trade — max 30% of portfolio value in a single position, max 50% total short exposure — while a RiskManager agent reviews proposed trades and advises before execution.
- **Observability.** A custom `TracingProcessor` writes every agent step (tool calls, generations, handoffs) to the database; the dashboard renders it as a live color-coded activity log per trader.

## Running it

Requires Python 3.12+ with [uv](https://docs.astral.sh/uv/), and Node for the frontend. Copy `.env.example` to `.env` and fill in your keys (only `OPENAI_API_KEY` and `TAVILY_API_KEY` are needed to start; without a Massive key, prices come from a deterministic simulator).

```bash
uv sync
cd frontend && npm install && cd ..
```

Three processes:

```bash
# 1. The API
uv run uvicorn backend.api:app --port 8000

# 2. The frontend (http://localhost:5173)
cd frontend && npm run dev

# 3. The trading engine
uv run -m backend.trading_floor
```

Interactive API docs at http://localhost:8000/docs. The engine runs every `RUN_EVERY_N_MINUTES` during market hours — keep an eye on your LLM API usage.

Reset all traders to their starting strategies with `uv run -m backend.reset`.

## Tests

```bash
uv run pytest
```

Covers the account mechanics (including shorts), the risk limits, and the price cache.

## Architecture notes

- The backend exposes a small read-only JSON API (`/api/traders`, `/api/traders/{name}`, `/api/traders/{name}/logs`, `/api/market`); the engine writes the SQLite database out of band. The Vite dev server proxies `/api`, so there is no CORS to configure.
- Sub-agents are wrapped as tools (`agent.as_tool(...)`) rather than handoffs: the trader stays in control and gets an answer back.
- Tool exposure is deliberately narrow — Tavily is filtered to plain search, and the RiskManager sees only the read-only account tools. Choosing what an agent can see is context engineering.
- Prices are cached briefly, and a stale cached price is preferred over the simulator when the market API is unavailable, so a portfolio never silently mixes real and synthetic prices.
- With `USE_MANY_MODELS=true`, each trader runs on a different provider (OpenAI, DeepSeek, Gemini, Grok) through OpenAI-compatible endpoints.

## Credits

The core simulation grew out of the capstone project of [Ed Donner's Agentic AI course](https://edwarddonner.com/curriculum), which I completed and then extended: short selling, deterministic risk limits plus a RiskManager agent, Qdrant semantic memory in place of the knowledge graph, a price cache for the market data free tier, and a test suite.
