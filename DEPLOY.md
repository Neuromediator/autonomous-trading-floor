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

Fill in the four keys at the top — `OPENAI_API_KEY`, `OPENROUTER_API_KEY`,
`MASSIVE_API_KEY`, `TAVILY_API_KEY`. The rest of the file already carries the
production schedule:

```
RUN_AT=15:00
RUN_EVEN_WHEN_MARKET_IS_CLOSED=true
```

`RUN_AT` is UTC and gives one round a day. US market hours are 13:30–20:00 UTC
in summer and 14:30–21:00 in winter, so a time between 15:00 and 19:00 stays
inside the window all year. `RUN_EVEN_WHEN_MARKET_IS_CLOSED=true` keeps the
round running on weekends and holidays instead of skipping it.

Everything else in `.env.example` is commented out and defaulted. Uncomment a
line to change it, but do not leave a variable set to an empty value — an empty
string overrides the default rather than falling back to it.

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

The database is the experiment's only record and nothing recreates it, so the
backup runs on a timer rather than by hand. `deploy/backup.sh` writes a dated
`sqlite3 .backup` snapshot plus a tarball of the agents' `memory/` into
`/var/backups/trading-floor` and keeps the last 14 days:

```bash
# as root
install -d -o trader -g trader /var/backups/trading-floor
cp /opt/trading-floor/deploy/trading-backup.service \
   /opt/trading-floor/deploy/trading-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now trading-backup.timer
```

The timer fires at 23:00 UTC, hours after a 15:00 round; move it if you move
`RUN_AT`. Check it with `systemctl list-timers trading-backup` and force a run
with `systemctl start trading-backup`.

This protects against a bad round or a wrong `sqlite3` command, not against
losing the disk — the copies sit on the same volume as the original. If the run
matters, pull them off the box as well, e.g. from your own machine:

```bash
rsync -az trader@YOUR_SERVER_IP:/var/backups/trading-floor/ ./backups/
```

## Updating

```bash
# as trader
cd /opt/trading-floor && git pull && uv sync
cd frontend && npm ci && npm run build && cd ..
# as root
systemctl restart trading-api trading-engine
```
