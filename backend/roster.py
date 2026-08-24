"""Who the traders are.

Kept apart from the engine so the accounts store and the API can check a name
against the same list without importing the agents SDK — accounts_server runs
as one of seven MCP subprocesses and has no business loading it.
"""

names = ["Warren", "George", "Ray", "Cathie"]
lastnames = ["Patience", "Bold", "Systematic", "Crypto"]
