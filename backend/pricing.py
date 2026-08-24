"""What a model call costs.

Prices come from OpenRouter's public model list, which needs no key and lists
the OpenAI catalogue alongside everyone else's — convenient, because three of
the four traders route through OpenRouter anyway and the fourth runs an OpenAI
model by its bare name.

They are cached in the database so the engine fetches once a day rather than
once a round, and so the API can price historical rows without network access.
A model the list does not carry is priced as None, never as zero: the tokens
are still recorded and the dashboard reports them as unpriced.
"""

import time
import urllib.request
import json

from .database import read_model_prices, write_model_prices

MODELS_URL = "https://openrouter.ai/api/v1/models"
PRICES_TTL_SECONDS = 24 * 3600

# Cached per process as well as in the database: a round prices a few hundred
# generation spans, and each one would otherwise be a query.
_cache: dict[str, tuple[float, float, float]] | None = None
_cache_read_at = 0.0
_CACHE_TTL_SECONDS = 300


def openrouter_id(model: str) -> str:
    """The name a model is listed under.

    A name with a "/" is already an OpenRouter id. A bare name is an OpenAI
    model — that is exactly how get_model routes it — and OpenRouter lists
    those under an "openai/" prefix.
    """
    return model if "/" in model else f"openai/{model}"


def refresh_prices() -> int:
    """Fetch the price list and cache it. Returns how many models were stored."""
    global _cache
    with urllib.request.urlopen(MODELS_URL, timeout=30) as response:
        payload = json.load(response)
    rows = []
    for entry in payload.get("data", []):
        pricing = entry.get("pricing") or {}
        try:
            rows.append((entry["id"], float(pricing["prompt"]), float(pricing["completion"])))
        except (KeyError, TypeError, ValueError):
            continue
    if rows:
        write_model_prices(rows)
        _cache = None
    return len(rows)


def prices() -> dict[str, tuple[float, float, float]]:
    global _cache, _cache_read_at
    if _cache is None or time.time() - _cache_read_at > _CACHE_TTL_SECONDS:
        _cache = read_model_prices()
        _cache_read_at = time.time()
    return _cache


def prices_are_stale() -> bool:
    """Whether the cache is empty or older than its TTL."""
    cached = prices()
    if not cached:
        return True
    newest = max(fetched_at for _, _, fetched_at in cached.values())
    return time.time() - newest > PRICES_TTL_SECONDS


def cost_of(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Cost in USD, or None when the model has no published price."""
    entry = prices().get(openrouter_id(model))
    if not entry:
        return None
    prompt, completion, _ = entry
    return input_tokens * prompt + output_tokens * completion
