#!/bin/sh
set -e
STAMP=$(date +%Y%m%d_%H%M%S)
DIR=${BACKUP_DIR:-./backups}
mkdir -p "$DIR"
FILE="$DIR/khatib_$STAMP.sql.gz"
PGHOST=${PGHOST:-db}
PGUSER=${PGUSER:-khatib}
PGDATABASE=${PGDATABASE:-khatib}
export PGPASSWORD=${POSTGRES_PASSWORD:-khatib_password_change_me}
pg_dump -h "$PGHOST" -U "$PGUSER" "$PGDATABASE" | gzip > "$FILE"
find "$DIR" -name 'khatib_*.sql.gz' -mtime +7 -delete 2>/dev/null || true
echo "Backup OK: $FILE"
