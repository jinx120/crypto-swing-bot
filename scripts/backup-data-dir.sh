#!/usr/bin/env bash
# Back up the swingbot data directory to a timestamped tarball before a live
# acceptance run (spec §Phase 6 step 1). Read-only with respect to the source.
#
# Usage: scripts/backup-data-dir.sh [DATA_DIR] [DEST_DIR]
#   DATA_DIR  defaults to $SWINGBOT_DATA_DIR or ~/.swingbot
#   DEST_DIR  defaults to $DATA_DIR/backups
set -euo pipefail

DATA_DIR="${1:-${SWINGBOT_DATA_DIR:-$HOME/.swingbot}}"
DEST_DIR="${2:-$DATA_DIR/backups}"

if [[ ! -d "$DATA_DIR" ]]; then
  echo "error: data dir not found: $DATA_DIR" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$DEST_DIR/swingbot-data-$STAMP.tar.gz"

# Exclude the backups dir itself to avoid recursive growth.
tar --exclude="$(basename "$DEST_DIR")" -czf "$ARCHIVE" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"

echo "backed up $DATA_DIR -> $ARCHIVE"
ls -lh "$ARCHIVE"
