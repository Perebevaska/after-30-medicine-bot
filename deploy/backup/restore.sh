#!/usr/bin/env bash
# Восстановление из дампа.
# Запуск: bash restore.sh /path/to/medbot_YYYYMMDD_HHMMSS.dump [целевой_DATABASE_URL]
set -euo pipefail

DUMP_FILE="${1:?Укажи путь к дампу: bash restore.sh /path/to/file.dump}"
TARGET_DSN="${2:-${DATABASE_URL:?DATABASE_URL не задан}}"

echo "[$(date -u +%FT%TZ)] Восстанавливаю из $DUMP_FILE → $TARGET_DSN"

# Пересоздаём схему и данные
pg_restore --clean --if-exists --no-owner --no-privileges \
    -d "$TARGET_DSN" "$DUMP_FILE"

echo "[$(date -u +%FT%TZ)] Восстановление завершено."

# Проверка количества строк
psql "$TARGET_DSN" -c "
SELECT 'users' AS tbl, COUNT(*) FROM users
UNION ALL SELECT 'medications', COUNT(*) FROM medications
UNION ALL SELECT 'schedule_rules', COUNT(*) FROM schedule_rules
UNION ALL SELECT 'intake_log', COUNT(*) FROM intake_log;
"
