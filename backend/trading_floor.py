from .traders import Trader
from typing import List
import asyncio
from .tracers import LogTracer
from agents import add_trace_processor, set_trace_processors
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
# The SDK uploads traces to OpenAI's dashboard, authorised with OPENAI_API_KEY
# even when no trader runs on an OpenAI model. Set OPENAI_TRACING=false to keep
# them local; the dashboard's activity log comes from LogTracer either way.
OPENAI_TRACING = os.getenv("OPENAI_TRACING", "true").strip().lower() == "true"

names = ["Warren", "George", "Ray", "Cathie"]
lastnames = ["Patience", "Bold", "Systematic", "Crypto"]

if USE_MANY_MODELS:
    # One model per trader, all from four different labs and all in the same
    # price class, so the comparison is between trading decisions rather than
    # between budgets. Frontier models were tried first and cost 30-50x as much
    # per run for no visible edge over a handful of rounds. The others go
    # through OpenRouter (the "/" in the name routes there); Warren goes to
    # OpenAI directly, which puts his raw requests in the platform's Responses
    # log. Traces reach the platform either way.
    model_names = [
        "gpt-5.6-luna",
        "z-ai/glm-4.7",
        "google/gemini-3.7-flash",
        "deepseek/deepseek-v4-flash",
    ]
    short_model_names = ["GPT 5.6 Luna", "GLM 4.7", "Gemini 3.7 Flash", "DeepSeek V4 Flash"]
else:
    model_names = ["gpt-5.6-luna"] * 4
    short_model_names = ["GPT 5.6 Luna"] * 4


def create_traders() -> List[Trader]:
    traders = []
    for name, lastname, model_name in zip(names, lastnames, model_names):
        traders.append(Trader(name, lastname, model_name))
    return traders


async def run_every_n_minutes():
    if OPENAI_TRACING:
        add_trace_processor(LogTracer())
    else:
        set_trace_processors([LogTracer()])
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
