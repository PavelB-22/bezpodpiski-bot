#!/bin/bash
# Установка бота на сервер (Ubuntu / Debian).  Запуск на сервере:  sudo bash setup.sh
set -e
APP=/opt/appsbot
cd "$(dirname "$0")"

echo "▶ Ставлю Python..."
apt-get update -qq && apt-get install -y -qq python3 python3-venv >/dev/null

echo "▶ Копирую бота в $APP..."
mkdir -p $APP
cp bot.py programs.json requirements.txt $APP/
[ -f .env ] && cp -n .env $APP/.env || true
[ -f $APP/.env ] || cp .env.example $APP/.env

python3 -m venv $APP/venv
$APP/venv/bin/pip install -q -r $APP/requirements.txt

cat > /etc/systemd/system/appsbot.service <<UNIT
[Unit]
Description=Telegram-бот бесплатных программ
After=network-online.target

[Service]
WorkingDirectory=$APP
ExecStart=$APP/venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable appsbot >/dev/null
systemctl restart appsbot
sleep 3
systemctl --no-pager status appsbot | head -12
echo
echo "✅ Бот установлен и запущен как сервис (сам поднимется после перезагрузки)."
echo "   Логи:        journalctl -u appsbot -f"
echo "   Настройки:   nano $APP/.env   → потом: systemctl restart appsbot"
