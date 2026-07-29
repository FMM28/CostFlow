#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

ENV_FILE="${PROJECT_ROOT}/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: No se encontró el archivo .env"
    exit 1
fi

load_env() {
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        [[ -z "${key// }" || "$key" =~ ^[[:space:]]*# ]] && continue

        key="$(echo "$key" | xargs)"
        value="$(echo "$value" | sed 's/^ *//;s/ *$//')"

        case "$key" in
            DB_HOST|DB_PORT|DB_NAME|DB_USER|DB_PASSWORD|BACKUP_DIR|RETENTION_DAYS)
                export "$key=$value"
                ;;
        esac
    done < "$ENV_FILE"
}

load_env

: "${DB_HOST:?DB_HOST no definido}"
: "${DB_PORT:=3306}"
: "${DB_NAME:?DB_NAME no definido}"
: "${DB_USER:?DB_USER no definido}"
: "${DB_PASSWORD:?DB_PASSWORD no definido}"

: "${BACKUP_DIR:=${PROJECT_ROOT}/backups}"
: "${RETENTION_DAYS:=7}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="${BACKUP_DIR}/costflow_${TIMESTAMP}.sql"

echo "Generando respaldo..."

MYSQL_PWD="$DB_PASSWORD" mariadb-dump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --user="$DB_USER" \
    --single-transaction \
    --quick \
    --skip-comments \
    --ignore-table="${DB_NAME}.alembic_version" \
    "$DB_NAME" \
    | gzip > "${BACKUP_FILE}.gz"

echo "Respaldo generado:"
echo "  ${BACKUP_FILE}.gz"

find "$BACKUP_DIR" \
    -type f \
    -name "*.sql.gz" \
    -mtime +"$RETENTION_DAYS" \
    -delete

echo "Proceso finalizado."