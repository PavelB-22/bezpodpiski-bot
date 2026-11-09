# Plan
- Python 3 + aiogram 3 (long polling — не нужен домен и HTTPS).
- bot.py — команды и кнопки; watcher — фоновая проверка GitHub раз в 10 минут.
- programs.json — каталог программ; state.json — какие версии уже опубликованы + счётчики.
- setup.sh — установка на Ubuntu/Debian VPS: venv + systemd-сервис appsbot.
