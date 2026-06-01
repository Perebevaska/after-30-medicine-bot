#!/bin/bash
# Создаёт пользователя medbot и базы данных medbot / medbot_test.
# Запуск: sudo bash setup_pg.sh
set -e
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='medbot'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE USER medbot WITH PASSWORD 'medbot';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='medbot'" | grep -q 1 \
  || sudo -u postgres createdb -O medbot medbot

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='medbot_test'" | grep -q 1 \
  || sudo -u postgres createdb -O medbot medbot_test

echo "Done: user medbot + databases medbot, medbot_test created."
