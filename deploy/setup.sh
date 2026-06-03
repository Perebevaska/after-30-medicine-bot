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
# D-2: прод отслеживает main — CI/CD деплоит только при push в main.
BRANCH="main"
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

read -rp "SSH-порт (Enter — 27027; введите 22 чтобы не менять): " SSH_PORT
SSH_PORT="${SSH_PORT:-27027}"

echo ""
info "Конфигурация:"
echo "  Домен:   $DOMAIN"
echo "  Bot:     ${BOT_TOKEN:0:10}..."
echo "  Admin:   $ADMIN_ID"
echo "  DB pass: ${DB_PASS:0:8}..."
echo "  SSH:     порт $SSH_PORT"
echo ""
read -rp "Всё верно? Продолжить установку? [y/N] " CONFIRM
[[ "${CONFIRM,,}" != "y" ]] && die "Установка отменена"

# ─── Системные пакеты ─────────────────────────────────────────────────────────

info "Обновление пакетов..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git python3 python3-venv python3-pip curl postgresql redis-server fonts-dejavu-core

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
REDIS_URL=redis://127.0.0.1:6379
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

cat > /etc/systemd/system/medbot-bot.service <<EOF
[Unit]
Description=Med Bot — Telegram бот напоминаний
After=network-online.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python3 bot.py
Restart=always
RestartSec=10s
StartLimitIntervalSec=300
StartLimitBurst=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/medbot-api.service <<EOF
[Unit]
Description=Med Bot — FastAPI
After=network-online.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5s
StartLimitIntervalSec=300
StartLimitBurst=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/medbot-worker.service <<EOF
[Unit]
Description=Med Bot — ARQ Worker (очередь Telegram-сообщений)
After=network-online.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/arq worker.WorkerSettings
Restart=always
RestartSec=10s
StartLimitIntervalSec=300
StartLimitBurst=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ─── journald: ограничение размера логов (OP4) ────────────────────────────────

info "Настройка journald (SystemMaxUse=200M)..."
mkdir -p /etc/systemd/journald.conf.d/
cat > /etc/systemd/journald.conf.d/medbot.conf <<EOF
[Journal]
SystemMaxUse=200M
EOF
systemctl restart systemd-journald
success "journald настроен ($(journalctl --disk-usage 2>/dev/null | grep -oP '[\d.]+ [A-Z]+' | head -1 || echo '?'))"

# ─── Caddyfile ────────────────────────────────────────────────────────────────

info "Настройка Caddy..."
# D-3: единый источник конфига — deploy/Caddyfile.template (рендер sed, без envsubst-зависимости).
sed -e "s|\${DOMAIN}|${DOMAIN}|g" -e "s|\${APP_DIR}|${APP_DIR}|g" \
    "${APP_DIR}/deploy/Caddyfile.template" > /etc/caddy/Caddyfile

# ─── Запуск сервисов ──────────────────────────────────────────────────────────

info "Запуск сервисов..."
# D-4: бэкап-юниты БД из репо + ежедневный таймер pg_dump (ротация 7 дней).
cp "${APP_DIR}/deploy/backup/medbot-backup.service" "${APP_DIR}/deploy/backup/medbot-backup.timer" /etc/systemd/system/
chmod +x "${APP_DIR}/deploy/backup/backup.sh"
systemctl daemon-reload
systemctl enable medbot-bot medbot-api medbot-worker caddy redis-server --quiet
systemctl enable --now medbot-backup.timer --quiet
systemctl restart redis-server
systemctl restart medbot-bot medbot-api medbot-worker caddy

# Проверка (OP1: systemctl is-active для всех сервисов)
sleep 5
for svc in medbot-bot medbot-api medbot-worker caddy redis-server; do
    if systemctl is-active --quiet "$svc"; then
        success "$svc запущен"
    else
        warn "$svc не запустился — проверьте: journalctl -u $svc -n 30"
    fi
done

# ─── Безопасность (hardening) ─────────────────────────────────────────────────
# Воспроизводит ручной аудит безопасности: ufw + fail2ban + swappiness + X11 off
# + смена SSH-порта через ssh.socket (Ubuntu 24.04 — socket-активация).
# Идемпотентно. Порт 22 НЕ срезается автоматически (защита от лок-аута) — см. вывод в конце.

info "Безопасность: firewall, fail2ban, sshd, sysctl..."
apt-get install -y -q ufw fail2ban

# .env — только владелец (внутри токен + пароль БД)
chmod 600 "${APP_DIR}/.env"

# swappiness 10 — меньше своп-долбёж диска при малой RAM
echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
sysctl -w vm.swappiness=10 >/dev/null

# X11Forwarding off — на сервере не нужен
if grep -q '^X11Forwarding yes' /etc/ssh/sshd_config; then
    sed -i 's/^X11Forwarding yes/X11Forwarding no/' /etc/ssh/sshd_config
fi
sshd -t || die "sshd_config невалиден после правки X11Forwarding"

# SSH-порт через ssh.socket override; держим И 22 И новый порт до ручной проверки
if [[ "$SSH_PORT" != "22" ]]; then
    mkdir -p /etc/systemd/system/ssh.socket.d
    cat > /etc/systemd/system/ssh.socket.d/override.conf <<EOF
[Socket]
ListenStream=
ListenStream=0.0.0.0:22
ListenStream=[::]:22
ListenStream=0.0.0.0:${SSH_PORT}
ListenStream=[::]:${SSH_PORT}
EOF
    systemctl daemon-reload
    systemctl restart ssh.socket
fi

# UFW — default deny incoming, разрешаем SSH(+22 temp)/HTTP/HTTPS
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow "${SSH_PORT}/tcp" comment 'ssh' >/dev/null
[[ "$SSH_PORT" != "22" ]] && ufw allow 22/tcp comment 'ssh-old-temp' >/dev/null
ufw allow 80/tcp comment 'http-caddy' >/dev/null
ufw allow 443/tcp comment 'https-caddy' >/dev/null
ufw --force enable >/dev/null

# fail2ban — jail sshd; journalmatch на ssh.service (socket-активация логирует туда)
F2B_PORTS="${SSH_PORT}"
[[ "$SSH_PORT" != "22" ]] && F2B_PORTS="22,${SSH_PORT}"
cat > /etc/fail2ban/jail.local <<EOF
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd

[sshd]
enabled  = true
port     = ${F2B_PORTS}
maxretry = 4
bantime  = 2h
journalmatch = _SYSTEMD_UNIT=ssh.service + _COMM=sshd
EOF
systemctl enable --now fail2ban >/dev/null 2>&1
systemctl restart fail2ban
success "Hardening применён (ufw + fail2ban + swappiness=10 + X11 off)"

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
echo "  Логи бота:    journalctl -u medbot-bot -f"
echo "  Логи API:     journalctl -u medbot-api -f"
echo "  Логи Worker:  journalctl -u medbot-worker -f"
echo "  Логи Caddy:   journalctl -u caddy -f"
echo ""
success "Бэкап БД: medbot-backup.timer включён (ежедневно, ротация 7 дней)"

if [[ "$SSH_PORT" != "22" ]]; then
    echo ""
    warn "SSH-порт сменён на ${SSH_PORT}, но порт 22 ОСТАВЛЕН открытым (защита от лок-аута)."
    warn "1) В ОТДЕЛЬНОМ терминале проверь:  ssh -p ${SSH_PORT} root@${DOMAIN}"
    warn "2) Убедившись что вход работает — сруби 22:"
    echo  "     printf '[Socket]\\nListenStream=\\nListenStream=0.0.0.0:${SSH_PORT}\\nListenStream=[::]:${SSH_PORT}\\n' > /etc/systemd/system/ssh.socket.d/override.conf"
    echo  "     systemctl daemon-reload && systemctl restart ssh.socket"
    echo  "     ufw delete allow 22/tcp"
    echo  "     sed -i 's/^port     = 22,${SSH_PORT}/port     = ${SSH_PORT}/' /etc/fail2ban/jail.local && systemctl restart fail2ban"
fi
