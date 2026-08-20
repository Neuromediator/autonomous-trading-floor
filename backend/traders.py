from contextlib import AsyncExitStack
from functools import lru_cache
from .accounts_client import read_accounts_resource, read_strategy_resource
from .tracers import make_trace_id
from agents import Agent, Tool, Runner, OpenAIChatCompletionsModel, trace
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os
import json
from .templates import (
    researcher_instructions,
    risk_manager_instructions,
    risk_manager_tool,
    trader_instructions,
    trade_message,
    rebalance_message,
    research_tool,
)
from .mcp_servers import trader_mcp_servers, researcher_mcp_servers, risk_manager_mcp_servers

load_dotenv(override=True)

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
GROK_BASE_URL = "https://api.x.ai/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

MAX_TURNS = 30

# Providers reachable with a key of their own, for a model name that mentions
# one and carries no "/". A name with a "/" goes to OpenRouter; a bare name the
# table doesn't match is an OpenAI model.
DIRECT_PROVIDERS = {
    "deepseek": ("DEEPSEEK_API_KEY", DEEPSEEK_BASE_URL),
    "grok": ("GROK_API_KEY", GROK_BASE_URL),
    "gemini": ("GOOGLE_API_KEY", GEMINI_BASE_URL),
}


@lru_cache(maxsize=None)
def provider_client(key_name: str, base_url: str) -> AsyncOpenAI:
    """A client for one provider, built on first use.

    The key is required rather than left to the OpenAI SDK, which silently falls
    back to OPENAI_API_KEY and would send it to another provider's endpoint.
    """
    api_key = os.getenv(key_name)
    if not api_key:
        raise RuntimeError(f"{key_name} is not set; it is required to reach {base_url}")
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def get_model(model_name: str):
    if "/" in model_name:
        client = provider_client("OPENROUTER_API_KEY", OPENROUTER_BASE_URL)
        return OpenAIChatCompletionsModel(model=model_name, openai_client=client)
    for provider, (key_name, base_url) in DIRECT_PROVIDERS.items():
        if provider in model_name:
            client = provider_client(key_name, base_url)
            return OpenAIChatCompletionsModel(model=model_name, openai_client=client)
    return model_name


async def get_researcher(mcp_servers, model_name) -> Agent:
    researcher = Agent(
        name="Researcher",
        instructions=researcher_instructions(),
        model=get_model(model_name),
        mcp_servers=mcp_servers,
    )
    return researcher


async def get_researcher_tool(mcp_servers, model_name) -> Tool:
    researcher = await get_researcher(mcp_servers, model_name)
    return researcher.as_tool(tool_name="Researcher", tool_description=research_tool())


async def get_risk_manager_tool(mcp_servers, model_name) -> Tool:
    risk_manager = Agent(
        name="RiskManager",
        instructions=risk_manager_instructions(),
        model=get_model(model_name),
        mcp_servers=mcp_servers,
    )
    return risk_manager.as_tool(tool_name="RiskManager", tool_description=risk_manager_tool())


class Trader:
    def __init__(self, name: str, lastname="Trader", model_name="gpt-5.6-luna"):
        self.name = name
        self.lastname = lastname
        self.agent = None
        self.model_name = model_name
        self.do_trade = True

    async def create_agent(self, trader_mcp_servers, researcher_mcp_servers, risk_mcp_servers) -> Agent:
        researcher = await get_researcher_tool(researcher_mcp_servers, self.model_name)
        risk_manager = await get_risk_manager_tool(risk_mcp_servers, self.model_name)
        self.agent = Agent(
            name=self.name,
            instructions=trader_instructions(self.name),
            model=get_model(self.model_name),
            tools=[researcher, risk_manager],
            mcp_servers=trader_mcp_servers,
        )
        return self.agent

    async def get_account_report(self) -> str:
        account = await read_accounts_resource(self.name)
        account_json = json.loads(account)
        account_json.pop("portfolio_value_time_series", None)
        return json.dumps(account_json)

    async def run_agent(self, trader_mcp_servers, researcher_mcp_servers, risk_mcp_servers):
        self.agent = await self.create_agent(trader_mcp_servers, researcher_mcp_servers, risk_mcp_servers)
        account = await self.get_account_report()
        strategy = await read_strategy_resource(self.name)
        message = (
            trade_message(self.name, strategy, account)
            if self.do_trade
            else rebalance_message(self.name, strategy, account)
        )
        await Runner.run(self.agent, message, max_turns=MAX_TURNS)

    async def run_with_mcp_servers(self):
        async with AsyncExitStack() as stack:
            trader_servers = [
                await stack.enter_async_context(server) for server in trader_mcp_servers()
            ]
            researcher_servers = [
                await stack.enter_async_context(server)
                for server in researcher_mcp_servers(self.name)
            ]
            risk_servers = [
                await stack.enter_async_context(server) for server in risk_manager_mcp_servers()
            ]
            await self.run_agent(trader_servers, researcher_servers, risk_servers)

    async def run_with_trace(self):
        trace_name = f"{self.name}-trading" if self.do_trade else f"{self.name}-rebalancing"
        trace_id = make_trace_id(f"{self.name.lower()}")
        with trace(trace_name, trace_id=trace_id):
            await self.run_with_mcp_servers()

    async def run(self):
        try:
            await self.run_with_trace()
        except Exception as e:
            print(f"Error running trader {self.name}: {e}")
        self.do_trade = not self.do_trade
