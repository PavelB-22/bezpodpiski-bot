"""
Бот для канала бесплатных программ.
  • выдаёт программы подписчикам канала (Mac / Windows);
  • сам публикует в канал пост, когда на GitHub выходит новая версия.
Запуск: python bot.py   (настройки — в файле .env рядом)
"""
import asyncio
import html
import json
import logging
import os
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

BASE = Path(__file__).parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")


# ---------- настройки ----------

def load_env(path: Path) -> None:
    """Простейшее чтение .env: строки КЛЮЧ=значение."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_env(BASE / ".env")
TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL = os.environ.get("CHANNEL", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or 0)
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "600") or 600)

PROGRAMS: list[dict] = json.loads((BASE / "programs.json").read_text(encoding="utf-8"))
PROG = {p["id"]: p for p in PROGRAMS}

STATE_FILE = BASE / "state.json"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"posted": {}, "downloads": {}}


def save_state() -> None:
    STATE_FILE.write_text(json.dumps(STATE, ensure_ascii=False, indent=2), encoding="utf-8")


STATE = load_state()
STATE.setdefault("posted", {})
STATE.setdefault("downloads", {})

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
BOT_USERNAME = ""


# ---------- GitHub ----------

_release_cache: dict[str, tuple[float, dict]] = {}


async def latest_release(repo: str, fresh: bool = False) -> dict | None:
    """Последний релиз с GitHub (кэш на 5 минут, чтобы не упираться в лимиты)."""
    loop = asyncio.get_running_loop()
    now = loop.time()
    if not fresh and repo in _release_cache and now - _release_cache[repo][0] < 300:
        return _release_cache[repo][1]
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": "apps-bot"}) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    log.warning("GitHub %s → %s", repo, r.status)
                    return None
                data = await r.json()
    except Exception as e:
        log.warning("GitHub недоступен: %s", e)
        return None
    _release_cache[repo] = (now, data)
    return data


def asset_url(release: dict | None, suffix: str) -> str | None:
    if not release:
        return None
    for a in release.get("assets", []):
        if a["name"].endswith(suffix):
            return a["browser_download_url"]
    return None


def release_notes(release: dict) -> str:
    """Берём из описания релиза только часть «что нового» (до блока установки)."""
    body = (release.get("body") or "").replace("\r", "")
    for marker in ("**Установка", "Установка одной строкой"):
        if marker in body:
            body = body.split(marker, 1)[0]
    body = body.replace("### Что нового", "").replace("**Что нового:**", "").strip()
    return body[:900]


# ---------- подписка ----------

async def is_subscribed(user_id: int) -> bool:
    if not CHANNEL:
        return True
    try:
        m = await bot.get_chat_member(CHANNEL, user_id)
        return m.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception as e:
        # Бот не админ в канале или канал указан неверно — не мешаем людям скачивать
        log.warning("Не могу проверить подписку (%s). Сделай бота админом канала.", e)
        return True


def channel_link() -> str:
    return f"https://t.me/{CHANNEL.lstrip('@')}" if CHANNEL.startswith("@") else "https://t.me/"


# ---------- клавиатуры ----------

def kb_menu() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{p['emoji']} {p['name']}", callback_data=f"p:{p['id']}")] for p in PROGRAMS]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_program(p: dict) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=pl["title"], callback_data=f"dl:{p['id']}:{key}")]
            for key, pl in p["platforms"].items()]
    rows.append([InlineKeyboardButton(text="◀️ Все программы", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_subscribe(prog_id: str, platform: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Подписаться на канал", url=channel_link())],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data=f"dl:{prog_id}:{platform}")],
    ])


# ---------- тексты ----------

MENU_TEXT = (
    "👋 Привет! Здесь бесплатные программы — замены платным.\n\n"
    "Выбери программу 👇"
)


def program_text(p: dict) -> str:
    return f"{p['emoji']} <b>{html.escape(p['name'])}</b>\n\n{html.escape(p['about'])}\n\nДля какого компьютера?"


async def install_text(p: dict, platform: str) -> str:
    pl = p["platforms"][platform]
    rel = await latest_release(p["repo"])
    version = rel.get("tag_name", "") if rel else ""
    direct = asset_url(rel, pl["asset"])
    lines = [
        f"{p['emoji']} <b>{html.escape(p['name'])}</b> {html.escape(version)}",
        f"{pl['title']}",
        "",
        html.escape(pl["how"]),
        f"<code>{html.escape(pl['install'])}</code>",
        "<i>(нажми на строку — она скопируется)</i>",
        "",
        "Программа поставится сама и дальше будет <b>обновляться автоматически</b>.",
    ]
    if direct:
        lines += ["", f"Или скачай файл вручную: <a href=\"{direct}\">ссылка</a>"]
    return "\n".join(lines)


# ---------- обработчики ----------

@dp.message(CommandStart())
async def on_start(m: Message, command: CommandObject):
    arg = (command.args or "").strip()
    if arg in PROG:
        p = PROG[arg]
        await m.answer(program_text(p), reply_markup=kb_program(p))
    else:
        await m.answer(MENU_TEXT, reply_markup=kb_menu())


@dp.callback_query(F.data == "menu")
async def on_menu(c: CallbackQuery):
    await c.message.edit_text(MENU_TEXT, reply_markup=kb_menu())
    await c.answer()


@dp.callback_query(F.data.startswith("p:"))
async def on_program(c: CallbackQuery):
    p = PROG.get(c.data.split(":", 1)[1])
    if p:
        await c.message.edit_text(program_text(p), reply_markup=kb_program(p))
    await c.answer()


@dp.callback_query(F.data.startswith("dl:"))
async def on_download(c: CallbackQuery):
    _, prog_id, platform = c.data.split(":", 2)
    p = PROG.get(prog_id)
    if not p or platform not in p["platforms"]:
        await c.answer("Программа не найдена", show_alert=True)
        return
    if not await is_subscribed(c.from_user.id):
        await c.message.edit_text(
            "🔒 Программы бесплатные — для подписчиков канала.\n\n"
            "Подпишись и нажми «Я подписался» 👇",
            reply_markup=kb_subscribe(prog_id, platform))
        await c.answer("Сначала подпишись на канал")
        return
    counter = STATE["downloads"].setdefault(prog_id, {})
    counter[platform] = counter.get(platform, 0) + 1
    save_state()
    await c.message.edit_text(await install_text(p, platform), disable_web_page_preview=True,
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                  [InlineKeyboardButton(text="◀️ Все программы", callback_data="menu")]]))
    await c.answer()


# ---------- команды для Павла ----------

def is_admin(m: Message) -> bool:
    return ADMIN_ID and m.from_user and m.from_user.id == ADMIN_ID


@dp.message(Command("post"))
async def on_post(m: Message, command: CommandObject):
    if not is_admin(m):
        return
    prog_id = (command.args or "").strip() or PROGRAMS[0]["id"]
    p = PROG.get(prog_id)
    if not p:
        await m.answer("Нет такой программы. Есть: " + ", ".join(PROG))
        return
    rel = await latest_release(p["repo"], fresh=True)
    if not rel:
        await m.answer("Не получилось получить версию с GitHub")
        return
    await post_release(p, rel)
    await m.answer("✅ Опубликовал в канал")


@dp.message(Command("stats"))
async def on_stats(m: Message):
    if not is_admin(m):
        return
    lines = ["📊 Нажатий «скачать»:"]
    for pid, by_platform in STATE["downloads"].items():
        total = sum(by_platform.values())
        detail = ", ".join(f"{k}: {v}" for k, v in by_platform.items())
        lines.append(f"• {PROG.get(pid, {}).get('name', pid)} — {total} ({detail})")
    if len(lines) == 1:
        lines.append("пока никто")
    await m.answer("\n".join(lines))


# ---------- автопост о новых версиях ----------

async def post_release(p: dict, rel: dict) -> None:
    tag = rel.get("tag_name", "")
    notes = release_notes(rel)
    text = f"🆕 <b>{html.escape(p['name'])}</b> — версия {html.escape(tag.lstrip('v'))}\n\n"
    if notes:
        text += f"<b>Что нового:</b>\n{html.escape(notes)}\n\n"
    text += "Если программа уже стоит — она обновится сама.\nНовенький? Жми кнопку 👇"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="📥 Скачать бесплатно", url=f"https://t.me/{BOT_USERNAME}?start={p['id']}")]])
    await bot.send_message(CHANNEL, text, reply_markup=kb, disable_web_page_preview=True)
    STATE["posted"][p["id"]] = tag
    save_state()
    log.info("Опубликован пост: %s %s", p["id"], tag)


async def release_watcher() -> None:
    await asyncio.sleep(5)
    while True:
        for p in PROGRAMS:
            rel = await latest_release(p["repo"], fresh=True)
            if not rel:
                continue
            tag = rel.get("tag_name")
            seen = STATE["posted"].get(p["id"])
            if seen is None:
                # Первый запуск — просто запоминаем текущую версию, без поста
                STATE["posted"][p["id"]] = tag
                save_state()
                continue
            if tag == seen:
                continue
            # Ждём, пока соберутся файлы для всех систем
            if all(asset_url(rel, pl["asset"]) for pl in p["platforms"].values()):
                try:
                    await post_release(p, rel)
                except Exception as e:
                    log.error("Не удалось опубликовать в канал: %s", e)
        await asyncio.sleep(CHECK_INTERVAL)


async def main() -> None:
    global BOT_USERNAME
    if not TOKEN or ":" not in TOKEN:
        raise SystemExit("❌ Заполни BOT_TOKEN в файле .env")
    me = await bot.get_me()
    BOT_USERNAME = me.username
    log.info("Бот @%s запущен. Канал: %s", BOT_USERNAME, CHANNEL)
    asyncio.create_task(release_watcher())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
