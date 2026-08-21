from .accounts import Account

# Seed strategies only, no personas: who each trader is now lives in their agent
# instructions (templates.PERSONAS), where a self-rewrite cannot erase it. What
# stays here is the opening tactical stance, which the traders are meant to
# replace as they learn.

warren_strategy = """
Hold a concentrated book of high-quality businesses bought below intrinsic value.
Favour steady cash flows, strong balance sheets and durable competitive advantages.
Size positions for the long term and let them run through market noise.
"""

george_strategy = """
Look for macro mispricings created by economic and geopolitical events.
Take contrarian positions when the evidence contradicts prevailing sentiment,
including short positions in assets that look overvalued. Act decisively on timing.
"""

ray_strategy = """
Build a diversified, risk-balanced book across asset classes using ETFs.
Weight positions by risk contribution rather than conviction, and adjust to
macro indicators, central bank policy and the phase of the economic cycle.
"""

cathie_strategy = """
Concentrate on crypto ETFs and disruptive innovation.
Accept volatility in exchange for exposure to structural growth, and rotate
between vehicles as regulation, yields and market sentiment change.
"""


def reset_traders():
    Account.get("Warren").reset(warren_strategy)
    Account.get("George").reset(george_strategy)
    Account.get("Ray").reset(ray_strategy)
    Account.get("Cathie").reset(cathie_strategy)


if __name__ == "__main__":
    reset_traders()
