#!/usr/bin/env bash
# Скрипт первичного развёртывания Med Bot на чистом Ubuntu VPS
# Запуск: bash <(curl -fsSL https://raw.githubusercontent.com/Perebevaska/after-30-medicine-bot/develop/deploy/setup.sh)

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && die "Запустите скрипт от root: sudo bash setup.sh"

REPO_URL="https://github.com/Perebevaska/after-30-medicine-bot.git"
BRANCH="develop"
APP_DIR="/root/after-30-medicine-bot"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║        Med Bot — Установка на VPS            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ─── Сбор конфигурации ────────────────────────────────────────────────────────

info "Введите параметры конфигурации (Enter — оставить значение по умолчанию)"
echo ""

read -rp "BOT_TOKEN (от @BotFather): " BOT_TOKEN
[[ -z "$BOT_TOKEN" ]] && die "BOT_TOKEN обязателен"

read -rp "ADMIN_ID (ваш Telegram ID, узнать у @userinfobot): " ADMIN_ID
[[ -z "$ADMIN_ID" ]] && die "ADMIN_ID обязателен"

read -rp "Домен сайта (например: medbot.isgood.host): " DOMAIN
[[ -z "$DOMAIN" ]] && die "Домен обязателен"

read -rp "Пароль для БД PostgreSQL (Enter — сгенерировать автоматически): " DB_PASS
if [[ -z "$DB_PASS" ]]; then
    DB_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40)
    warn "Сгенерирован пароль БД: ${DB_PASS}"
    warn "Сохраните его в надёжном месте!"
fi

read -rp "RATE_LIMIT_PER_MINUTE (по умолчанию: 60): " RATE_LIMIT
RATE_LIMIT="${RATE_LIMIT:-60}"

echo ""
info "Конфигурация:"
echo "  Домен:   $DOMAIN"
echo "  Bot:     ${BOT_TOKEN:0:10}..."
echo "  Admin:   $ADMIN_ID"
echo "  DB pass: ${DB_PASS:0:8}..."
echo ""
read -rp "Всё верно? Продолжить установку? [y/N] " CONFIRM
[[ "${CONFIRM,,}" != "y" ]] && die "Установка отменена"

# ─── Системные пакеты ─────────────────────────────────────────────────────────

info "Обновление пакетов..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git python3 python3-venv python3-pip curl postgresql fonts-dejavu-core

# ─── Node.js 22 ───────────────────────────────────────────────────────────────

if ! node --version 2>/dev/null | grep -q "v2[0-9]"; then
    info "Установка Node.js 22..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null 2>&1
    apt-get install -y -q nodejs
fi
success "Node.js $(node --version)"

# ─── Caddy ────────────────────────────────────────────────────────────────────

if ! command -v caddy &>/dev/null; then
    info "Установка Caddy..."
    apt-get install -y -q debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    apt-get update -q && apt-get install -y -q caddy
fi
success "Caddy $(caddy version | head -1)"

# ─── PostgreSQL ───────────────────────────────────────────────────────────────

info "Настройка PostgreSQL..."
systemctl enable postgresql --quiet
systemctl start postgresql
# Ждём готовности
for i in {1..10}; do pg_isready -q && break || sleep 2; done
pg_isready -q || die "PostgreSQL не запустился"

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='medbot'" | grep -q 1 \
    || sudo -u postgres psql -c "CREATE USER medbot WITH PASSWORD '${DB_PASS}';" >/dev/null
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='medbot'" | grep -q 1 \
    || sudo -u postgres psql -c "CREATE DATABASE medbot OWNER medbot;" >/dev/null
# Обновляем пароль если пользователь уже существовал
sudo -u postgres psql -c "ALTER USER medbot WITH PASSWORD '${DB_PASS}';" >/dev/null

success "PostgreSQL готов"

# ─── Клонирование репозитория ─────────────────────────────────────────────────

if [[ -d "$APP_DIR/.git" ]]; then
    info "Обновление репозитория..."
    git -C "$APP_DIR" fetch origin
    git -C "$APP_DIR" checkout "$BRANCH"
    git -C "$APP_DIR" pull origin "$BRANCH"
else
    info "Клонирование репозитория..."
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
success "Репозиторий: $APP_DIR"

cd "$APP_DIR"

# ─── .env ─────────────────────────────────────────────────────────────────────

info "Создание .env..."
cat > .env <<EOF
BOT_TOKEN=${BOT_TOKEN}
ADMIN_ID=${ADMIN_ID}
DATABASE_URL=postgresql://medbot:${DB_PASS}@127.0.0.1/medbot
MINIAPP_ORIGIN=https://${DOMAIN}
RATE_LIMIT_PER_MINUTE=${RATE_LIMIT}
TRUST_PROXY=true
EOF
chmod 600 .env
success ".env создан"

# ─── Python venv ──────────────────────────────────────────────────────────────

info "Установка Python-зависимостей..."
python3 -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements.txt
success "Python venv готов"

# ─── Инициализация БД ─────────────────────────────────────────────────────────

info "Инициализация таблиц БД..."
venv/bin/python3 - <<'PYEOF'
from dotenv import load_dotenv; load_dotenv()
import os
from database import init_pool, init_db
init_pool(os.environ['DATABASE_URL'])
init_db()
print("Таблицы созданы")
PYEOF
success "База данных инициализирована"

# ─── Сборка Mini App ──────────────────────────────────────────────────────────

info "Сборка Mini App..."
cd miniapp
rm -rf node_modules package-lock.json
npm install --silent
npm run build --silent
cd ..
# Права для Caddy
chmod o+x /root
chmod -R o+rX miniapp/dist
success "Mini App собран"

# ─── systemd-сервисы ──────────────────────────────────────────────────────────

info "Создание systemd-сервисов..."

cat > /etc/systemd/system/medbot.service <<EOF
[Unit]
Description=Med Bot — Telegram бот напоминаний
After=network-online.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python3 bot.py
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/medbot-api.service <<EOF
[Unit]
Description=Med Bot — FastAPI
After=network-online.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ─── Caddyfile ────────────────────────────────────────────────────────────────

info "Настройка Caddy..."
cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {
    handle /api/* {
        uri strip_prefix /api
        reverse_proxy 127.0.0.1:8000
    }

    handle {
        root * ${APP_DIR}/miniapp/dist
        try_files {path} /index.html
        file_server
    }
}
EOF

# ─── Запуск сервисов ──────────────────────────────────────────────────────────

info "Запуск сервисов..."
systemctl daemon-reload
systemctl enable medbot medbot-api caddy --quiet
systemctl restart medbot medbot-api caddy

# Проверка
sleep 5
for svc in medbot medbot-api caddy; do
    if systemctl is-active --quiet "$svc"; then
        success "$svc запущен"
    else
        warn "$svc не запустился — проверьте: journalctl -u $svc -n 30"
    fi
done

# ─── Финальная проверка ───────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║           Установка завершена!               ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
info "Проверка API..."
sleep 3
if curl -sf "https://${DOMAIN}/api/health" | grep -q "ok"; then
    success "https://${DOMAIN}/api/health — OK"
else
    warn "API ещё не отвечает (Caddy может получать сертификат). Подождите 30 сек и проверьте вручную."
fi

echo ""
echo "  Mini App:  https://${DOMAIN}/"
echo "  API:       https://${DOMAIN}/api/health"
echo ""
echo "  Логи бота:  journalctl -u medbot -f"
echo "  Логи API:   journalctl -u medbot-api -f"
echo "  Логи Caddy: journalctl -u caddy -f"
echo ""
warn "Не забудьте настроить бэкап БД: deploy/backup/backup.sh"
