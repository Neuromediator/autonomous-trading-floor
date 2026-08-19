from .traders import Trader
from typing import List
import asyncio
from .tracers import LogTracer
from agents import add_trace_processor
from .market import is_market_open
from dotenv import load_dotenv
import os

load_dotenv(override=True)

RUN_EVERY_N_MINUTES = int(os.getenv("RUN_EVERY_N_MINUTES", "60"))
# Pause between traders within one round: they run one after another, not in
# parallel, so four agents don't burst through LLM and market-data rate limits.
SECONDS_BETWEEN_TRADERS = int(os.getenv("SECONDS_BETWEEN_TRADERS", "60"))
RUN_EVEN_WHEN_MARKET_IS_CLOSED = (
    os.getenv("RUN_EVEN_WHEN_MARKET_IS_CLOSED", "false").strip().lower() == "true"
)
USE_MANY_MODELS = os.getenv("USE_MANY_MODELS", "true").strip().lower() == "true"

names = ["Warren", "George", "Ray", "Cathie"]
lastnames = ["Patience", "Bold", "Systematic", "Crypto"]

if USE_MANY_MODELS:
    # One model per trader, picked from the artificialanalysis.ai leaderboard for
    # cost/quality balance on agentic tool use (Aug 2026). Grok and DeepSeek are
    # reached through OpenRouter (the "/" in the name routes there).
    model_names = [
        "gpt-5.6-sol",
        "x-ai/grok-4.5",
        "gemini-3.7-flash",
        "deepseek/deepseek-v4-flash",
    ]
    short_model_names = ["GPT 5.6 Sol", "Grok 4.5", "Gemini 3.7 Flash", "DeepSeek V4 Flash"]
else:
    model_names = ["gpt-5.6-luna"] * 4
    short_model_names = ["GPT 5.6 Luna"] * 4


def create_traders() -> List[Trader]:
    traders = []
    for name, lastname, model_name in zip(names, lastnames, model_names):
        traders.append(Trader(name, lastname, model_name))
    return traders


async def run_every_n_minutes():
    add_trace_processor(LogTracer())
    traders = create_traders()
    while True:
        if RUN_EVEN_WHEN_MARKET_IS_CLOSED or is_market_open():
            for i, trader in enumerate(traders):
                if i:
                    await asyncio.sleep(SECONDS_BETWEEN_TRADERS)
                await trader.run()
        else:
            print("Market is closed, skipping run")
        await asyncio.sleep(RUN_EVERY_N_MINUTES * 60)


if __name__ == "__main__":
    print(f"Starting scheduler to run every {RUN_EVERY_N_MINUTES} minutes")
    asyncio.run(run_every_n_minutes())
