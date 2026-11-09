# Telegram-бот бесплатных программ

## Что умеет
- **/start** — меню программ → выбор Mac/Windows → проверка подписки на канал → команда установки одной строкой.
- **Автопост**: вышла новая версия на GitHub → через ~10 минут пост в канале с «что нового» и кнопкой «📥 Скачать бесплатно».
- **/post shepot** — опубликовать пост вручную, **/stats** — сколько раз скачивали (только для тебя, ADMIN_ID).

## Установка / обновление на сервере
1. На Маке: `cd ~/Projects/TelegramBot && bash publish.sh` — отправит бота на GitHub.
2. На сервере (консоль VDSina или ssh) одна строка:
   `git -C /root/TelegramBot pull 2>/dev/null || git clone https://github.com/PavelB-22/bezpodpiski-bot /root/TelegramBot; bash /root/TelegramBot/setup.sh`
   В первый раз скрипт спросит токен бота.

## Добавить новую программу
Допиши запись в `programs.json` (по образцу Shepot), скопируй файл на сервер и `systemctl restart appsbot`.
