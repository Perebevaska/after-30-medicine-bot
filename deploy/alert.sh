#!/usr/bin/env bash
# OP3: уведомление админу в Telegram при сбое systemd-сервиса.
# Вызывается из medbot-alert@.service (OnFailure=). $1 = имя упавшего юнита.
set -uo pipefail

UNIT="${1:-unknown}"
ENV_FILE="/root/after-30-medicine-bot/.env"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

if [ -z "${BOT_TOKEN:-}" ] || [ -z "${ADMIN_ID:-}" ]; then
  echo "alert: BOT_TOKEN/ADMIN_ID не заданы — пропуск" >&2
  exit 0
fi

HOST="$(hostname)"
WHEN="$(date '+%Y-%m-%d %H:%M:%S %Z')"
LOG="$(journalctl -u "$UNIT" -n 8 --no-pager -o cat 2>/dev/null | tail -8)"

TEXT="🚨 Сбой сервиса: ${UNIT}
Хост: ${HOST}
Время: ${WHEN}

Последние строки лога:
${LOG}"

curl -fsS --max-time 10 \
  "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${ADMIN_ID}" \
  --data-urlencode "text=${TEXT}" >/dev/null || true
