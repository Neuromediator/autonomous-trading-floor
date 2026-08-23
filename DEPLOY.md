# Deploying to a server

The engine and the API share `accounts.db` as a file, so they must run on the
same host with the same disk. One small VPS is enough: a round spawns seven MCP
subprocesses and the memory server loads a ~130 MB embedding model, so budget
2 GB of RAM at minimum and 4 GB comfortably.

**Everything below runs on the server, over SSH.** The only command you type on
your own machine is the `ssh` in step 2. Each block says which user it expects:
`root` for anything that installs software or writes outside the project, and
`trader` — the unprivileged account the services run as — for the rest.

These notes assume Ubuntu 24.04 and a DuckDNS subdomain. The systemd units in
`deploy/` use `/opt/trading-floor` and a user called `trader`; adjust both to
taste, in the units as well as here.

## 1. Create the server

Any provider will do. Hetzner's CX22 (2 vCPU, 4 GB, 40 GB, about €4.50 a month)
is more than enough. Choose Ubuntu 24.04 and add your SSH key during creation.
Write down the IPv4 address it gives you.

## 2. Point the subdomain at it

Register a subdomain at [duckdns.org](https://www.duckdns.org) and set its IP to
the address from step 1. The IP is static, so this is a one-off — no update
daemon needed. Then connect:

```bash
# on your own machine
ssh root@YOUR_SERVER_IP
```

Everything from here on is typed in that SSH session.

## 3. Install what the project needs

```bash
# as root
apt update && apt install -y curl git sqlite3
# Node 22 for the frontend build; Ubuntu's own package is too old for Vite.
curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt install -y nodejs

# The service account, and a directory it owns.
adduser --disabled-password --gecos "" trader
mkdir -p /opt/trading-floor
chown trader:trader /opt/trading-floor
```

Install [Caddy](https://caddyserver.com/docs/install#debian-ubuntu-raspbian)
from its APT repository while you are still root.

## 4. Install the project

```bash
# as trader
su - trader
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env          # puts uv on PATH for this session

git clone https://github.com/Neuromediator/autonomous-trading-floor /opt/trading-floor
cd /opt/trading-floor
uv sync
cd frontend && npm ci && npm run build && cd ..
```

The build lands in `frontend/dist`, which the API serves itself — there is no
separate web server for the page, and no CORS to configure.

## 5. Configuration

```bash
# as trader, in /opt/trading-floor
cp .env.example .env
nano .env
chmod 600 .env
```

Fill in the API keys, and for an unattended run set:

```
RUN_AT=15:00
RUN_EVEN_WHEN_MARKET_IS_CLOSED=false
```

`RUN_AT` is UTC and gives one round a trading day. US market hours are
13:30–20:00 UTC in summer and 14:30–21:00 in winter, so a time between 15:00 and
19:00 stays inside the window all year. Leave `RUN_AT` empty and the engine
falls back to interval mode, which is for testing.

Check it runs before handing it to systemd:

```bash
uv run python -c "from backend.trading_floor import model_names; print(model_names)"
```

## 6. Start the services

```bash
# back as root: exit the trader shell first
exit
cp /opt/trading-floor/deploy/trading-api.service \
   /opt/trading-floor/deploy/trading-engine.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now trading-api trading-engine
```

Both restart on failure. Watch them with:

```bash
systemctl status trading-engine
journalctl -u trading-engine -f
```

The engine prints when each round starts, when it finishes, and when it skips a
closed market, so the journal alone tells you whether the schedule is holding.

## 7. HTTPS

Put your subdomain in the Caddyfile — replace `your-subdomain.duckdns.org` —
then install it:

```bash
# as root
nano /opt/trading-floor/deploy/Caddyfile
cp /opt/trading-floor/deploy/Caddyfile /etc/caddy/Caddyfile
systemctl reload caddy
```

Caddy answers the ACME challenge on port 80 and serves the dashboard on 443, so
both must be open. Leave port 8000 closed to the outside: the API only needs to
be reachable from Caddy over localhost.

## 8. Check it

```bash
curl -s https://your-subdomain.duckdns.org/api/market
```

It should report the price tier and whether the market is open. The dashboard
itself is at the root of the same host.

## Backups

The database is the experiment's only record and nothing recreates it. A daily
copy is enough:

```bash
sqlite3 /opt/trading-floor/accounts.db ".backup /opt/trading-floor/backup.db"
```

The agents' Qdrant memory lives in `memory/` and is equally unrecoverable; copy
it with the same cadence if the run matters.

## Updating

```bash
# as trader
cd /opt/trading-floor && git pull && uv sync
cd frontend && npm ci && npm run build && cd ..
# as root
systemctl restart trading-api trading-engine
```
