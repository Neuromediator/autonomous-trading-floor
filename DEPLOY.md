# Deploying to a server

The engine and the API share `accounts.db` as a file, so they must run on the
same host with the same disk. One small VPS is enough: a round spawns seven MCP
subprocesses and the memory server loads a ~130 MB embedding model, so budget
2 GB of RAM at minimum and 4 GB comfortably.

These notes assume Ubuntu 24.04 and a DuckDNS subdomain. Adjust paths and the
user name to taste; the systemd units in `deploy/` use `/opt/trading-floor` and
a user called `trader`.

## 1. The DNS name

Register a subdomain at [duckdns.org](https://www.duckdns.org) and point its A
record at the server's IP. Hetzner and most providers give a static IP, so this
is a one-off — no update daemon needed.

## 2. The server

```bash
adduser --disabled-password --gecos "" trader
apt update && apt install -y curl git
# Node 22 for the frontend build; Ubuntu's own package is too old for Vite.
curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt install -y nodejs
```

Install [Caddy](https://caddyserver.com/docs/install#debian-ubuntu-raspbian) from
its APT repository, then as the `trader` user:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/Neuromediator/autonomous-trading-floor /opt/trading-floor
cd /opt/trading-floor
uv sync
cd frontend && npm ci && npm run build && cd ..
```

The build lands in `frontend/dist`, which the API serves itself — there is no
separate web server for the page, and no CORS to configure.

## 3. Configuration

Copy `.env.example` to `.env` and fill in the keys. For an unattended run:

```bash
RUN_AT=15:00                     # UTC, once a trading day
RUN_EVEN_WHEN_MARKET_IS_CLOSED=false
```

`RUN_AT` is UTC. US market hours are 13:30–20:00 UTC in summer and 14:30–21:00
in winter, so a time between 15:00 and 19:00 stays inside the window all year.
Without `RUN_AT` the engine falls back to interval mode, which is for testing.

Keep `.env` readable only by the service user: `chmod 600 .env`.

## 4. The services

```bash
sudo cp deploy/trading-api.service deploy/trading-engine.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-api trading-engine
```

Both restart on failure. Watch them with:

```bash
systemctl status trading-engine
journalctl -u trading-engine -f
```

The engine prints when each round starts, when it finishes, and when it skips a
closed market, so the journal alone tells you whether the schedule is holding.

## 5. HTTPS

Put your subdomain in `deploy/Caddyfile`, then:

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy answers the ACME challenge on port 80 and serves the dashboard on 443, so
open both in the firewall and leave port 8000 closed to the outside — the API
only needs to be reachable from Caddy on localhost.

## 6. Checks

```bash
curl -s https://your-subdomain.duckdns.org/api/market
```

Should report the price tier and whether the market is open. The dashboard
itself is at the root of the same host.

## Backups

The database is the experiment's only record and nothing recreates it. A daily
copy is enough:

```bash
sqlite3 /opt/trading-floor/accounts.db ".backup /opt/trading-floor/backup.db"
```

The agents' Qdrant memory lives in `memory/` and is equally unrecoverable; copy
it with the same cadence if the run matters.
