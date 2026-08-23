from .traders import Trader
from typing import List
import asyncio
import time
import traceback
from datetime import datetime, timedelta, timezone
from .database import prune_old_rows
from .tracers import LogTracer
from agents import add_trace_processor, set_trace_processors
from .market import is_market_open
from dotenv import load_dotenv
import os

load_dotenv(override=True)

# A daily run is scheduled by wall clock, not by sleeping a fixed span: the
# sleep started when the previous round *finished*, so each day drifted later by
# the length of a round and after a few weeks the engine woke to a closed market
# and never ran again. RUN_AT is UTC ("15:00"); pick a time inside US market
# hours all year, which run 13:30-20:00 UTC in summer and 14:30-21:00 in winter.
RUN_AT = os.getenv("RUN_AT", "").strip()
RUN_EVERY_N_MINUTES = int(os.getenv("RUN_EVERY_N_MINUTES", "60"))
if RUN_EVERY_N_MINUTES <= 0:
    raise ValueError(f"RUN_EVERY_N_MINUTES must be a positive number of minutes, got {RUN_EVERY_N_MINUTES}")
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


def parse_run_at(run_at: str) -> tuple[int, int]:
    """Parse a UTC "HH:MM" into (hour, minute), rejecting anything else.

    Called once at import so a typo fails immediately with a readable message.
    Left to the scheduler it raised hours later, deep in the run loop, and
    systemd's Restart=always turned that into the same stack trace every
    RestartSec with nothing saying which variable was wrong.
    """
    parts = run_at.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f'RUN_AT must be a UTC "HH:MM" time, got {run_at!r}')
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f'RUN_AT must be a UTC "HH:MM" time, got {run_at!r}')
    return hour, minute


def seconds_until(run_at: str, now: datetime | None = None) -> float:
    """Seconds until the next occurrence of a UTC HH:MM."""
    now = now or datetime.now(timezone.utc)
    hour, minute = parse_run_at(run_at)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_round(traders: List[Trader]) -> None:
    """One round: every trader in turn, with a pause so they don't burst limits."""
    if not (RUN_EVEN_WHEN_MARKET_IS_CLOSED or is_market_open()):
        print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC — market closed, skipping round")
        return
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC — starting round")
    for i, trader in enumerate(traders):
        if i:
            await asyncio.sleep(SECONDS_BETWEEN_TRADERS)
        await trader.run()
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC — round finished")


async def run_round_safely(traders: List[Trader]) -> None:
    """run_round, but a failure costs one round instead of the process.

    An unhandled exception — a network blip, a refused LLM call, an MCP
    subprocess that died — used to propagate out of run_forever and end the
    process. systemd then restarted it, which in RUN_AT mode skipped to
    tomorrow's slot and lost the day, and in interval mode started a whole new
    round every RestartSec.
    """
    try:
        await run_round(traders)
    except asyncio.CancelledError:
        raise
    except Exception:
        print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC — round failed, waiting for the next one:")
        traceback.print_exc()


async def run_forever():
    if OPENAI_TRACING:
        add_trace_processor(LogTracer())
    else:
        set_trace_processors([LogTracer()])
    logs, searches = prune_old_rows()
    if logs or searches:
        print(f"Pruned {logs} expired log rows and {searches} cached searches")
    traders = create_traders()

    if RUN_AT:
        while True:
            wait = seconds_until(RUN_AT)
            print(f"Next round at {RUN_AT} UTC, in {wait / 3600:.1f} hours")
            await asyncio.sleep(wait)
            await run_round_safely(traders)

    # Interval mode, for testing. The next start is measured from this start,
    # not from the finish, so rounds keep their place in the day.
    period = RUN_EVERY_N_MINUTES * 60
    next_start = time.monotonic()
    while True:
        await run_round_safely(traders)
        # A round can outrun its slot: four agents with a pause between them
        # take well over an hour. Skip the slots that went by instead of
        # firing rounds back to back until the schedule catches up.
        next_start += period
        now = time.monotonic()
        if next_start <= now:
            skipped = int((now - next_start) // period) + 1
            next_start += skipped * period
            print(f"Round overran its slot; skipping {skipped} scheduled {'round' if skipped == 1 else 'rounds'}")
        await asyncio.sleep(next_start - now)


# Fail at import, not hours later inside the scheduler.
if RUN_AT:
    parse_run_at(RUN_AT)


if __name__ == "__main__":
    if RUN_AT:
        print(f"Starting scheduler: one round a day at {RUN_AT} UTC")
    else:
        print(f"Starting scheduler: a round every {RUN_EVERY_N_MINUTES} minutes")
    asyncio.run(run_forever())
