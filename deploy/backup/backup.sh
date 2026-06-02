#!/usr/bin/env bash
# Бэкап PostgreSQL с ротацией 7 дней.
# Запуск: bash backup.sh
# Переменные: DATABASE_URL, BACKUP_DIR (по умолчанию ~/backups/medbot)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/medbot}"
mkdir -p "$BACKUP_DIR"

FILENAME="medbot_$(date -u +%Y%m%d_%H%M%S).dump"
FILEPATH="$BACKUP_DIR/$FILENAME"

echo "[$(date -u +%FT%TZ)] Создаю бэкап → $FILEPATH"
pg_dump "${DATABASE_URL}" -Fc -f "$FILEPATH"

SIZE=$(du -sh "$FILEPATH" | cut -f1)
echo "[$(date -u +%FT%TZ)] Готово: $FILENAME ($SIZE)"

# Ротация: удаляем файлы старше 7 дней
DELETED=$(find "$BACKUP_DIR" -name "medbot_*.dump" -mtime +7 -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && echo "[$(date -u +%FT%TZ)] Удалено устаревших: $DELETED"
