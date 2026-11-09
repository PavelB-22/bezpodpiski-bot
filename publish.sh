#!/bin/bash
# Отправить бота на GitHub (на Маке):  bash publish.sh
set -e
cd "$(dirname "$0")"
[ -d .git ] || git init -b main
git add -A
git commit -m "Бот $(date '+%Y-%m-%d %H:%M')" || echo "(нет новых изменений)"
git remote | grep -q origin || git remote add origin https://github.com/PavelB-22/bezpodpiski-bot.git
git push -u origin main
echo
echo "✅ Бот на GitHub. На сервере (консоль VDSina) выполни:"
echo "   git -C /root/TelegramBot pull 2>/dev/null || git clone https://github.com/PavelB-22/bezpodpiski-bot /root/TelegramBot; bash /root/TelegramBot/setup.sh"
