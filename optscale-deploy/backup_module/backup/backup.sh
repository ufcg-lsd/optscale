#!/bin/bash
set -uo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/backups/$TIMESTAMP"
CLICKHOUSE_DATA_DIR="$BACKUP_DIR/clickhouse_data"
mkdir -p "$BACKUP_DIR" "$CLICKHOUSE_DATA_DIR"

# Track what succeeded/failed for summary
MARIADB_STATUS="skipped"
MONGO_STATUS="skipped"
CLICKHOUSE_STATUS="skipped"
RABBITMQ_STATUS="skipped"
UPLOAD_STATUS="skipped"

echo "--- Starting Full Database Dump $TIMESTAMP ---"

# Required env vars:
# MARIADB_ROOT_PASSWORD, MONGO_ROOT_PASSWORD, CLICKHOUSE_PASSWORD, RABBITMQ_PASSWORD
# S3_BUCKET, S3_PREFIX
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION

# ─────────────────────────────────────────────
# 1. MariaDB (schema + data)
# ─────────────────────────────────────────────
echo ""
echo "[1/5] Backing up MariaDB..."
if mysqldump \
    -h mariadb \
    -u root \
    -p"$MARIADB_ROOT_PASSWORD" \
    --all-databases \
    --single-transaction \
    --routines \
    --triggers \
    --events \
    > "$BACKUP_DIR/mariadb.sql" 2>/tmp/mariadb_err.txt; then
  echo "MariaDB backup complete."
  MARIADB_STATUS="ok"
else
  echo "ERROR: MariaDB backup failed. Skipping."
  cat /tmp/mariadb_err.txt || true
  rm -f "$BACKUP_DIR/mariadb.sql"
  MARIADB_STATUS="FAILED"
fi

# ─────────────────────────────────────────────
# 2. MongoDB (data only, no auth/user metadata)
# ─────────────────────────────────────────────
echo ""
echo "[2/5] Backing up MongoDB..."
if mongodump \
    --host mongo-discovery \
    --username root \
    --password "$MONGO_ROOT_PASSWORD" \
    --authenticationDatabase admin \
    --db restapi \
    --archive="$BACKUP_DIR/mongo.archive" \
    2>/tmp/mongo_err.txt; then
  echo "MongoDB backup complete."
  MONGO_STATUS="ok"
else
  echo "ERROR: MongoDB backup failed. Skipping."
  cat /tmp/mongo_err.txt || true
  rm -f "$BACKUP_DIR/mongo.archive"
  MONGO_STATUS="FAILED"
fi

# ─────────────────────────────────────────────
# 3. ClickHouse (schemas + table data)
# ─────────────────────────────────────────────
echo ""
echo "[3/5] Backing up ClickHouse schemas and data..."

CH_FAIL=0

mapfile -t CLICKHOUSE_DATABASES < <(
  clickhouse-client \
    --host clickhouse \
    --user default \
    --password "$CLICKHOUSE_PASSWORD" \
    --query "SHOW DATABASES" 2>/tmp/ch_err.txt \
  | grep -Ev '^(system|information_schema|INFORMATION_SCHEMA)$'
) || CH_FAIL=1

if [ "$CH_FAIL" -eq 1 ]; then
  echo "ERROR: Could not connect to ClickHouse. Skipping."
  cat /tmp/ch_err.txt || true
  CLICKHOUSE_STATUS="FAILED"
else
  CLICKHOUSE_STATUS="ok"
  for db in "${CLICKHOUSE_DATABASES[@]}"; do
    [ -z "$db" ] && continue

    echo "  Backing up ClickHouse database schema: $db"
    if ! clickhouse-client \
        --host clickhouse \
        --user default \
        --password "$CLICKHOUSE_PASSWORD" \
        --query "SHOW CREATE DATABASE \`$db\`" \
        > "$BACKUP_DIR/clickhouse_${db}_schema.sql" 2>/tmp/ch_err.txt; then
      echo "  WARNING: Failed to back up schema for database $db. Skipping database."
      cat /tmp/ch_err.txt || true
      CLICKHOUSE_STATUS="partial"
      continue
    fi

    DB_DIR="$CLICKHOUSE_DATA_DIR/$db"
    mkdir -p "$DB_DIR"

    mapfile -t TABLES < <(
      clickhouse-client \
        --host clickhouse \
        --user default \
        --password "$CLICKHOUSE_PASSWORD" \
        --query "SHOW TABLES FROM \`$db\`" 2>/tmp/ch_err.txt
    ) || { echo "  WARNING: Could not list tables for $db. Skipping."; cat /tmp/ch_err.txt || true; continue; }

    for table in "${TABLES[@]}"; do
      [ -z "$table" ] && continue

      echo "  Backing up ClickHouse table schema: $db.$table"
      if ! clickhouse-client \
          --host clickhouse \
          --user default \
          --password "$CLICKHOUSE_PASSWORD" \
          --query "SHOW CREATE TABLE \`$db\`.\`$table\`" \
          > "$DB_DIR/${table}.schema.sql" 2>/tmp/ch_err.txt; then
        echo "  WARNING: Failed schema for $db.$table. Skipping table."
        cat /tmp/ch_err.txt || true
        CLICKHOUSE_STATUS="partial"
        continue
      fi

      echo "  Backing up ClickHouse table data: $db.$table"
      if ! clickhouse-client \
          --host clickhouse \
          --user default \
          --password "$CLICKHOUSE_PASSWORD" \
          --query "SELECT * FROM \`$db\`.\`$table\` FORMAT Native" \
          > "$DB_DIR/${table}.native" 2>/tmp/ch_err.txt; then
        echo "  WARNING: Failed data dump for $db.$table. Skipping table data."
        cat /tmp/ch_err.txt || true
        rm -f "$DB_DIR/${table}.native"
        CLICKHOUSE_STATUS="partial"
      fi
    done
  done

  echo "ClickHouse backup complete (status: $CLICKHOUSE_STATUS)."
fi

# ─────────────────────────────────────────────
# 4. RabbitMQ (definitions only)
# ─────────────────────────────────────────────
echo ""
echo "[4/5] Backing up RabbitMQ definitions..."

HTTP_STATUS=$(curl -s -o "$BACKUP_DIR/rabbitmq_defs.json" -w "%{http_code}" \
  -u optscale:"$RABBITMQ_PASSWORD" \
  http://rabbitmq:15672/api/definitions 2>/tmp/rabbitmq_err.txt) || HTTP_STATUS="000"

if [ "$HTTP_STATUS" = "200" ]; then
  echo "RabbitMQ definitions backup complete."
  echo "NOTE: Queue message contents are not included."
  RABBITMQ_STATUS="ok"
else
  echo "ERROR: RabbitMQ backup failed with HTTP $HTTP_STATUS. Skipping."
  cat /tmp/rabbitmq_err.txt || true
  rm -f "$BACKUP_DIR/rabbitmq_defs.json"
  RABBITMQ_STATUS="FAILED (HTTP $HTTP_STATUS)"
fi

# ─────────────────────────────────────────────
# 5. Manifest + Upload to S3
# ─────────────────────────────────────────────
echo ""
echo "[5/5] Creating manifest and uploading to S3..."

{
  echo "timestamp=$TIMESTAMP"
  echo "created_at=$(date -Iseconds)"
  echo "mariadb=$MARIADB_STATUS"
  echo "mongodb=$MONGO_STATUS"
  echo "clickhouse=$CLICKHOUSE_STATUS"
  echo "rabbitmq=$RABBITMQ_STATUS"
  echo "---files---"
  find "$BACKUP_DIR" -maxdepth 5 -type f | sort
} > "$BACKUP_DIR/backup_manifest.txt"

if aws s3 cp "$BACKUP_DIR/" "s3://$S3_BUCKET/$S3_PREFIX/$TIMESTAMP/" --recursive 2>/tmp/s3_err.txt; then
  echo "Backup uploaded to s3://$S3_BUCKET/$S3_PREFIX/$TIMESTAMP/"
  UPLOAD_STATUS="ok"
else
  echo "ERROR: S3 upload failed."
  cat /tmp/s3_err.txt || true
  UPLOAD_STATUS="FAILED"
fi

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
echo ""
echo "======================================"
echo "   Backup Summary — $TIMESTAMP"
echo "======================================"
echo "  MariaDB    : $MARIADB_STATUS"
echo "  MongoDB    : $MONGO_STATUS"
echo "  ClickHouse : $CLICKHOUSE_STATUS"
echo "  RabbitMQ   : $RABBITMQ_STATUS"
echo "  S3 Upload  : $UPLOAD_STATUS"
echo "======================================"

if [ "$UPLOAD_STATUS" = "FAILED" ]; then
  echo "CRITICAL: S3 upload failed. Exiting with error."
  exit 1
fi

echo "Backup job finished."
