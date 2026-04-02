#!/bin/bash
set -euo pipefail

# Required environment variables:
# S3_BUCKET, S3_PREFIX, TIMESTAMP
# MARIADB_ROOT_PASSWORD, MONGO_ROOT_PASSWORD, CLICKHOUSE_PASSWORD, RABBITMQ_PASSWORD
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
# Optional: AWS_SESSION_TOKEN

BACKUP_DIR="/tmp/restore/$TIMESTAMP"
CLICKHOUSE_DATA_DIR="$BACKUP_DIR/clickhouse_data"
mkdir -p "$BACKUP_DIR"

# Track what succeeded/failed for summary
MARIADB_STATUS="skipped"
MONGO_STATUS="skipped"
CLICKHOUSE_STATUS="skipped"
RABBITMQ_STATUS="skipped"

echo "--- Starting Restore from S3 Backup $TIMESTAMP ---"

# ─────────────────────────────────────────────
# Download backup files from S3
# ─────────────────────────────────────────────
echo ""
echo "Downloading backup files from s3://$S3_BUCKET/$S3_PREFIX/$TIMESTAMP/"
aws s3 cp "s3://$S3_BUCKET/$S3_PREFIX/$TIMESTAMP/" "$BACKUP_DIR/" --recursive

echo "Downloaded files:"
find "$BACKUP_DIR" -type f | sort

# Validate manifest
if [ -f "$BACKUP_DIR/backup_manifest.txt" ]; then
  echo ""
  echo "Backup manifest:"
  cat "$BACKUP_DIR/backup_manifest.txt"
else
  echo "WARNING: No backup_manifest.txt found. Proceeding anyway."
fi

echo ""

# ─────────────────────────────────────────────
# 1. Restore MariaDB
# ─────────────────────────────────────────────
echo "[1/4] Restoring MariaDB..."
if [ -f "$BACKUP_DIR/mariadb.sql" ]; then
  if mysql \
      -h mariadb \
      -u root \
      -p"$MARIADB_ROOT_PASSWORD" \
      < "$BACKUP_DIR/mariadb.sql" 2>/tmp/mariadb_err.txt; then
    echo "MariaDB restore complete."
    MARIADB_STATUS="ok"
  else
    echo "ERROR: MariaDB restore failed."
    cat /tmp/mariadb_err.txt || true
    MARIADB_STATUS="FAILED"
  fi
else
  echo "WARNING: mariadb.sql not found, skipping MariaDB restore."
  MARIADB_STATUS="skipped (file missing)"
fi

echo ""

# ─────────────────────────────────────────────
# 2. Restore MongoDB (no auth/user metadata)
# ─────────────────────────────────────────────
echo "[2/4] Restoring MongoDB..."
if mongorestore \
      --host mongo-discovery \
      --username root \
      --password "$MONGO_ROOT_PASSWORD" \
      --authenticationDatabase admin \
      --db restapi \
      --archive="$BACKUP_DIR/mongo.archive" \
      --drop \
      2>/tmp/mongo_err.txt; then
    echo "MongoDB restore complete."
    MONGO_STATUS="ok"
  else
    echo "ERROR: MongoDB restore failed."
    cat /tmp/mongo_err.txt || true
    MONGO_STATUS="FAILED"
  fi
else
  echo "WARNING: mongo.archive not found, skipping MongoDB restore."
  MONGO_STATUS="skipped (file missing)"
fi

echo ""

# ─────────────────────────────────────────────
# 3. Restore ClickHouse (schemas + table data)
# ─────────────────────────────────────────────
echo "[3/4] Restoring ClickHouse..."
if [ ! -d "$CLICKHOUSE_DATA_DIR" ]; then
  echo "WARNING: clickhouse_data directory not found, skipping ClickHouse restore."
  CLICKHOUSE_STATUS="skipped (directory missing)"
else
  CLICKHOUSE_STATUS="ok"

  # Restore database-level schemas first
  for db_schema_file in "$BACKUP_DIR"/clickhouse_*_schema.sql; do
    [ -f "$db_schema_file" ] || continue
    echo "  Restoring ClickHouse database schema: $(basename "$db_schema_file")"
    if ! clickhouse-client \
        --host clickhouse \
        --user default \
        --password "$CLICKHOUSE_PASSWORD" \
        --multiquery < "$db_schema_file" 2>/tmp/ch_err.txt; then
      echo "  WARNING: Failed to restore schema $(basename "$db_schema_file")"
      cat /tmp/ch_err.txt || true
      CLICKHOUSE_STATUS="partial"
    fi
  done

  # Restore per-table schemas and data
  for db_dir in "$CLICKHOUSE_DATA_DIR"/*/; do
    [ -d "$db_dir" ] || continue
    db=$(basename "$db_dir")
    echo "  Restoring ClickHouse tables for database: $db"

    # Restore table schemas first
    for table_schema_file in "$db_dir"*.schema.sql; do
      [ -f "$table_schema_file" ] || continue
      table=$(basename "$table_schema_file" .schema.sql)
      echo "    Restoring table schema: $db.$table"
      if ! clickhouse-client \
          --host clickhouse \
          --user default \
          --password "$CLICKHOUSE_PASSWORD" \
          --multiquery < "$table_schema_file" 2>/tmp/ch_err.txt; then
        echo "    WARNING: Failed schema for $db.$table"
        cat /tmp/ch_err.txt || true
        CLICKHOUSE_STATUS="partial"
      fi
    done

    # Restore table data
    for table_data_file in "$db_dir"*.native; do
      [ -f "$table_data_file" ] || continue
      table=$(basename "$table_data_file" .native)

      if [ ! -s "$table_data_file" ]; then
        echo "    Skipping empty data file for: $db.$table"
        continue
      fi

      echo "    Restoring table data: $db.$table"
      if ! clickhouse-client \
          --host clickhouse \
          --user default \
          --password "$CLICKHOUSE_PASSWORD" \
          --query "INSERT INTO \`$db\`.\`$table\` FORMAT Native" \
          < "$table_data_file" 2>/tmp/ch_err.txt; then
        echo "    WARNING: Failed data restore for $db.$table"
        cat /tmp/ch_err.txt || true
        CLICKHOUSE_STATUS="partial"
      fi
    done
  done

  echo "ClickHouse restore complete (status: $CLICKHOUSE_STATUS)."
fi

echo ""

# ─────────────────────────────────────────────
# 4. Restore RabbitMQ definitions
# ─────────────────────────────────────────────
echo "[4/4] Restoring RabbitMQ definitions..."
if [ -f "$BACKUP_DIR/rabbitmq_defs.json" ]; then
  HTTP_STATUS=$(curl -s -o /tmp/rabbitmq_restore_response.txt -w "%{http_code}" \
    -u optscale:"$RABBITMQ_PASSWORD" \
    -H "Content-Type: application/json" \
    -X POST \
    -d @"$BACKUP_DIR/rabbitmq_defs.json" \
    http://rabbitmq:15672/api/definitions 2>/tmp/rabbitmq_err.txt) || HTTP_STATUS="000"

  if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "201" ] || [ "$HTTP_STATUS" = "204" ]; then
    echo "RabbitMQ definitions restored successfully (HTTP $HTTP_STATUS)."
    RABBITMQ_STATUS="ok"
  else
    echo "ERROR: RabbitMQ restore failed with HTTP $HTTP_STATUS"
    cat /tmp/rabbitmq_restore_response.txt || true
    RABBITMQ_STATUS="FAILED (HTTP $HTTP_STATUS)"
  fi
else
  echo "WARNING: rabbitmq_defs.json not found, skipping RabbitMQ restore."
  RABBITMQ_STATUS="skipped (file missing)"
fi

echo ""

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
echo "======================================"
echo "   Restore Summary — $TIMESTAMP"
echo "======================================"
echo "  MariaDB    : $MARIADB_STATUS"
echo "  MongoDB    : $MONGO_STATUS"
echo "  ClickHouse : $CLICKHOUSE_STATUS"
echo "  RabbitMQ   : $RABBITMQ_STATUS"
echo "======================================"
echo ""
echo "NOTE: RabbitMQ queue message contents are not restorable via definitions export."
echo "--- Restore Completed ---"
