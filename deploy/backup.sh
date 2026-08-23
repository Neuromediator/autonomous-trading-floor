#!/usr/bin/env bash
# A dated, consistent copy of the trading floor's database and the agents'
# memory. Run by trading-backup.timer; safe to run by hand at any time.
set -euo pipefail

SRC=${SRC:-/opt/trading-floor}
DEST=${DEST:-/var/backups/trading-floor}
KEEP_DAYS=${KEEP_DAYS:-14}

stamp=$(date -u +%Y%m%d-%H%M)
mkdir -p "$DEST"

# sqlite3 .backup rather than cp: it takes a read lock and writes a consistent
# snapshot even while a round is running, and it folds in the -wal sidecar. A
# plain copy of accounts.db alone can restore as a torn database.
sqlite3 "$SRC/accounts.db" ".backup '$DEST/accounts-$stamp.db'"

# The agents' Qdrant memory is plain files and just as unrecoverable. Nothing
# holds it open between rounds, which is why the timer fires outside one.
if [ -d "$SRC/memory" ]; then
    tar czf "$DEST/memory-$stamp.tar.gz" -C "$SRC" memory
fi

find "$DEST" -maxdepth 1 -name 'accounts-*.db' -mtime +"$KEEP_DAYS" -delete
find "$DEST" -maxdepth 1 -name 'memory-*.tar.gz' -mtime +"$KEEP_DAYS" -delete

echo "Backed up to $DEST, keeping $KEEP_DAYS days"
