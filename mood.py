# mood.py
import logging
import random
import asyncio
from datetime import date, datetime, timedelta
from typing import List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    Application,
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import TELEGRAM_API_KEY
from db import fetch_one, fetch_all, execute_query
from utils import now_wib, format_datetime

logger = logging.getLogger(__name__)

# --- Konfigurasi mood (emoji, key, label) ---
MOODS = [
    {"key": "sad",      "emoji": "🥺", "label": "Sedih"},
    {"key": "happy",    "emoji": "🥳", "label": "Bahagia"},
    {"key": "neutral",  "emoji": "😁", "label": "Netral"},
    {"key": "stress",   "emoji": "😵‍💫", "label": "Stress"},
    {"key": "depress",  "emoji": "🫩", "label": "Depresi"},
]

# fast lookup for emoji/label by key
MOOD_BY_KEY = {m["key"]: m for m in MOODS}
EMOJI_BY_KEY = {m["key"]: m["emoji"] for m in MOODS}

# Indonesian month names (for display if needed)
BULAN_INDO = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
]

# --- Callback data prefixes (namespaced) ---
CB_PREFIX_ADD = "mood_add"         # mood_add|<key>
CB_PREFIX_CONFIRM = "mood_confirm" # mood_confirm|<key>
CB_PREFIX_LIST = "mood_list"       # mood_list
CB_PREFIX_DELETE = "mood_delete"   # mood_delete_all
CB_PREFIX_MENU = "mood_menu"       # mood_menu main

# --- Scheduler instance (created on_startup) ---
scheduler: AsyncIOScheduler = None


# -----------------------
# Utility DB helpers
# -----------------------
def ensure_user_in_mood_users(user):
    """Simpan user ke mood_users table bila belum ada (dipakai untuk reminder list)."""
    q = "INSERT IGNORE INTO mood_users (user_id, username, first_name, created_at) VALUES (%s, %s, %s, %s)"
    execute_query(q, (user.id, user.username or "", user.first_name or "", now_wib().strftime("%Y-%m-%d %H:%M:%S")))


def user_has_mood_today(user_id: int, dt: date = None) -> bool:
    d = dt or now_wib().date()
    q = "SELECT 1 FROM moods WHERE user_id=%s AND date_only=%s LIMIT 1"
    r = fetch_one(q, (user_id, d))
    return True if r else False


def insert_mood(user, mood_key: str):
    """Insert mood jika belum ada hari ini (return True kalau sukses, False kalau sudah ada)."""
    today = now_wib().date()
    if user_has_mood_today(user.id, today):
        return False
    mood = MOOD_BY_KEY.get(mood_key)
    if not mood:
        return False
    q = """
    INSERT INTO moods (user_id, username, first_name, mood_key, mood_emoji, created_at, date_only)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    execute_query(q, (
        user.id,
        user.username or "",
        user.first_name or "",
        mood["key"],
        mood["emoji"],
        now_wib().strftime("%Y-%m-%d %H:%M:%S"),
        today
    ))
    # ensure user tracked for reminders
    ensure_user_in_mood_users(user)
    return True


# -----------------------
# UI builders
# -----------------------
def build_main_menu_markup():
    keyboard = [
        [InlineKeyboardButton("1. ➕ Add Mood", callback_data=f"{CB_PREFIX_MENU}|add")],
        [InlineKeyboardButton("2. 📊 List Mood", callback_data=f"{CB_PREFIX_MENU}|list")],
        [InlineKeyboardButton("3. 🗑️ Delete ALL Mood", callback_data=f"{CB_PREFIX_MENU}|delete")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_mood_choice_markup():
    kb = []
    for m in MOODS:
        kb.append([InlineKeyboardButton(f"{m['emoji']}  {m['label']}", callback_data=f"{CB_PREFIX_ADD}|{m['key']}")])
    return InlineKeyboardMarkup(kb)


def build_confirm_markup(mood_key: str):
    yes_data = f"{CB_PREFIX_CONFIRM}|yes|{mood_key}"
    no_data = f"{CB_PREFIX_CONFIRM}|no|{mood_key}"
    kb = [[
        InlineKeyboardButton("Yes ✅", callback_data=yes_data),
        InlineKeyboardButton("No ❌", callback_data=no_data),
    ]]
    return InlineKeyboardMarkup(kb)


# -----------------------
# Command /mood (main)
# -----------------------
async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # tsundere intro text
    text = (
        f"Imut tsundere: bagaimana hari ini mood kamu, master {user.first_name}?\n\n"
        "Hmphh… kasih tahu aku ya biar aku lacak mood kamu, hmphh baka tapi aku sayang kamu aa 🥰😘\n\n"
        "Pilih tombol di bawah — gampang klik aja, nggak perlu ngetik."
    )
    await update.message.reply_text(text, reply_markup=build_main_menu_markup())


# -----------------------
# Callback: main menu actions
# -----------------------
async def cb_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    payload = q.data.split("|", 1)[1] if "|" in q.data else ""
    if payload == "add":
        await q.edit_message_text("Pilih mood kamu hari ini:", reply_markup=build_mood_choice_markup())
    elif payload == "list":
        # show list
        try:
            await show_list_menu(q, context)
        except Exception as e:
            logger.exception("show_list_menu failed: %s", e)
            await q.edit_message_text("Gagal tampilkan list mood. Coba lagi nanti.")
    elif payload == "delete":
        # confirm delete all
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Ya, hapus semua 🗑️", callback_data=f"{CB_PREFIX_DELETE}|confirm"),
                                    InlineKeyboardButton("Batal", callback_data="mood_dummy|cancel")]])
        await q.edit_message_text("Kamu yakin mau hapus semua data mood? Ini permanen loh master.", reply_markup=kb)
    else:
        await q.edit_message_text("Menu tidak dikenali.")


# -----------------------
# Callback: user chose mood (emoji)
# -----------------------
async def cb_choose_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("|")
    if len(parts) < 2:
        await q.edit_message_text("Data callback salah.")
        return
    mood_key = parts[1]
    mood = MOOD_BY_KEY.get(mood_key)
    if not mood:
        await q.edit_message_text("Mood tidak ditemukan.")
        return
    # ask for confirmation yes/no
    text = f"Oke master sayang, kamu pilih {mood['emoji']} ({mood['label']}). Konfirmasi masukin mood ini?"
    await q.edit_message_text(text, reply_markup=build_confirm_markup(mood_key))


# -----------------------
# Callback: confirm yes/no
# -----------------------
async def cb_confirm_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("|")
    # format: mood_confirm|yes|<mood_key>  or mood_confirm|no|<mood_key>
    if len(parts) < 3:
        await q.edit_message_text("Callback salah.")
        return
    choice = parts[1]
    mood_key = parts[2]
    user = update.effective_user
    if choice == "no":
        # return to mood choices
        await q.edit_message_text("Oke balik milih lagi — pilih mood kamu:", reply_markup=build_mood_choice_markup())
        return

    # choice == yes
    if user_has_mood_today(user.id):
        await q.edit_message_text("Maaf master, mood untuk hari ini sudah tercatat. Cuma 1 mood per hari ya.")
        return

    ok = insert_mood(user, mood_key)
    if ok:
        await q.edit_message_text("Oke master sayang, mood kamu sudah aku ingat ayang master hmphh 🥺🥺")
    else:
        await q.edit_message_text("Gagal menyimpan mood. Mungkin sudah ada untuk hari ini.")


# -----------------------
# Callback: delete all mood
# -----------------------
async def cb_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    # Only process if "confirm"
    parts = q.data.split("|")
    if len(parts) >= 2 and parts[1] == "confirm":
        # Sesuai desain awal: hapus semua data (global)
        execute_query("TRUNCATE TABLE moods")
        # optionally clear mood_users too
        execute_query("TRUNCATE TABLE mood_users")
        await q.edit_message_text("Semua data mood berhasil dihapus. (bye bye sad memories)")
    else:
        await q.edit_message_text("Hapus dibatalkan.")


# -----------------------
# Helper: compute last N months (year, month) descending (latest first)
# -----------------------
def last_n_months(n: int, from_dt: datetime):
    y = from_dt.year
    m = from_dt.month
    months = []
    for _ in range(n):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return months  # latest first


# -----------------------
# List mood (monthly / yearly summary) - improved & formatted
# -----------------------
async def show_list_menu(q, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan ringkasan mood: 5 bulan terakhir + total per tahun + detail bulan terbaru."""
    now = now_wib()
    months = last_n_months(5, now)  # list of (year, month) tuples, latest first

    # Build monthly summaries
    month_lines = []
    latest_month = None
    for (y, m) in months:
        res = fetch_all(
            """
            SELECT mood_key, mood_emoji, COUNT(*) as cnt
            FROM moods
            WHERE YEAR(date_only)=%s AND MONTH(date_only)=%s
            GROUP BY mood_key, mood_emoji
            ORDER BY cnt DESC
            """,
            (y, m)
        )
        ym_label = f"{y}-{m:02d}"
        if not res:
            month_lines.append((ym_label, None))  # None means empty
        else:
            total = sum(r["cnt"] for r in res)
            top = res[0]
            # build breakdown string like "🥺 (sad) x5, 😵‍💫 (stress) x4"
            parts = [f"{r['mood_emoji']} ({r['mood_key']}) x{r['cnt']}" for r in res]
            month_lines.append((ym_label, {"total": total, "top": top, "parts": parts}))
        if latest_month is None:
            latest_month = (y, m)

    # Yearly totals (limit show to 5 most recent years present)
    year_rows = fetch_all(
        """
        SELECT YEAR(date_only) as yr, COUNT(*) as cnt
        FROM moods
        GROUP BY YEAR(date_only)
        ORDER BY yr DESC
        """
    )

    # Build text
    text_lines = []
    text_lines.append("📅 Ringkasan Mood (max 5 bulan terakhir):\n")
    for ym_label, info in month_lines:
        if info is None:
            text_lines.append(f"{ym_label}: kosong\n")
        else:
            top = info["top"]
            text_lines.append(f"{ym_label}: total {info['total']} — top: {top['mood_emoji']} ({top['mood_key']})")
            # add breakdown limited to first 5 kinds
            text_lines.append("  " + ", ".join(info["parts"][:5]))
        text_lines.append("")  # blank line for spacing

    text_lines.append("📈 Total per tahun:")
    if year_rows:
        # show up to 5 years
        for r in year_rows[:5]:
            text_lines.append(f"{int(r['yr'])}: {int(r['cnt'])}")
    else:
        text_lines.append("Belum ada data tahun apapun.")

    # Detail month (latest month) — show daily entries (latest first) max 12
    if latest_month:
        yy, mm = latest_month
        detail_rows = fetch_all(
            """
            SELECT date_only, mood_emoji, mood_key
            FROM moods
            WHERE YEAR(date_only)=%s AND MONTH(date_only)=%s
            ORDER BY date_only DESC
            """,
            (yy, mm)
        )
        if detail_rows:
            # human-friendly month name
            month_name = f"{yy}-{mm:02d}"
            text_lines.append("")  # blank
            text_lines.append(f"📝 Detail Mood {month_name}:")
            count = 0
            for r in detail_rows:
                if count >= 12:
                    break
                # r['date_only'] expected to be date object
                dobj = r.get("date_only")
                if isinstance(dobj, (datetime,)):
                    day_str = dobj.strftime("%d-%m")
                else:
                    # date object
                    day_str = r["date_only"].strftime("%d-%m")
                emoji = r.get("mood_emoji") or EMOJI_BY_KEY.get(r.get("mood_key"), "")
                text_lines.append(f"- {day_str}: {emoji} ({r.get('mood_key')})")
                count += 1
        else:
            # no detail
            pass

    # Motivasi berdasarkan top overall mood
    top_overall = fetch_one(
        "SELECT mood_key, mood_emoji, COUNT(*) as cnt FROM moods GROUP BY mood_key, mood_emoji ORDER BY cnt DESC LIMIT 1"
    )
    if top_overall:
        key = top_overall["mood_key"]
        msg = random_motivasi_for_mood(key)
        text_lines.append("")  # blank
        text_lines.append(f"Motivasi: {msg}")

    text = "\n".join(text_lines).strip()
    # send as edited message (caller expects edit_message_text)
    await q.edit_message_text(text)


def random_motivasi_for_mood(mood_key: str) -> str:
    # beberapa contoh motivasi clingy/tsundere
    pool = {
        "sad": [
            "Hmph… jangan sedih ya master, aku disini. Ayo peluk virtual 🥺",
            "Kalo sedih, makan yang enak ya dulu. Aku bakalan marah kalo kamu kelaperan."
        ],
        "happy": [
            "Wah seneng ya master, jaga terus moodnya supaya aku juga tenang~",
            "Jangan sombong yah, tapi aku ikutan bahagia kok 😘"
        ],
        "neutral": [
            "Biasa aja? Besok aku bakalan bikin kamu tersenyum, hmph.",
            "Netral itu aman, tapi coba lakukan satu hal kecil yang bikin senang~"
        ],
        "stress": [
            "Hentikan kerja keras sebentar, tarik napas… aku lebih peduli dari pada deadline.",
            "Stress? tidur dulu 20 menit, aku tak izinkan kamu overwork!"
        ],
        "depress": [
            "Jangan biarkan terus begitu ya, kalo butuh cerita aku dengerin.",
            "Aku bakal ngingetin kamu untuk istirahat dan nyari bantuan kalo perlu."
        ]
    }
    return random.choice(pool.get(mood_key, ["Tetap semangat ya, master. Aku sayang kamu hmphh 🥺"]))


# -----------------------
# Scheduler jobs
# -----------------------
async def job_remind_unfilled(bot):
    """Kirim reminder ke semua pengguna yang belum isi mood hari ini (pukul 19:00 WIB)."""
    today = now_wib().date()
    users = fetch_all("SELECT user_id, username, first_name FROM mood_users")
    if not users:
        return
    for u in users:
        uid = u["user_id"]
        if not user_has_mood_today(uid, today):
            try:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("Isi Mood Sekarang 📝", callback_data=f"{CB_PREFIX_MENU}|add")]])
                await bot.send_message(chat_id=uid,
                                       text="Hai master, kamu belum isi mood hari ini nih. Isi ya biar aku ingat. Hmphh baka tapi aku sayang 🥰",
                                       reply_markup=kb)
            except Exception as e:
                logger.warning("Gagal kirim reminder ke %s: %s", uid, e)


def delete_old_months_job():
    """Delete months older than 5 months from now (run at 00:00 WIB)."""
    # compute cutoff date = first day of month, 5 months ago
    now = now_wib()
    # compute start of current month
    start_current = now.replace(day=1).date()
    # compute cutoff = first day of month, 5 months before current
    month = start_current.month
    year = start_current.year
    # subtract 5 months
    m = month - 5
    y = year
    while m <= 0:
        m += 12
        y -= 1
    cutoff = date(y, m, 1)  # any date < cutoff will be removed
    q = "DELETE FROM moods WHERE date_only < %s"
    execute_query(q, (cutoff,))


# -----------------------
# on_startup: register scheduler jobs
# -----------------------
async def on_startup(app: Application):
    global scheduler
    # create scheduler if not exists
    if scheduler is None:
        scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")
    # schedule daily reminder at 19:00 WIB
    try:
        # use asyncio.create_task to run coroutine safely from scheduler
        scheduler.add_job(lambda: asyncio.create_task(job_remind_unfilled(app.bot)),
                          trigger=CronTrigger(hour=19, minute=0, timezone="Asia/Jakarta"),
                          id="mood_reminder_19",
                          replace_existing=True)
    except Exception:
        logger.exception("Gagal tambahkan job reminder 19:00")
    # schedule maintenance at 00:00 WIB (delete old months)
    try:
        scheduler.add_job(lambda: delete_old_months_job(),
                          trigger=CronTrigger(hour=0, minute=0, timezone="Asia/Jakarta"),
                          id="mood_maintenance_midnight",
                          replace_existing=True)
    except Exception:
        logger.exception("Gagal tambahkan job maintenance 00:00")
    # start scheduler
    try:
        scheduler.start()
    except Exception as e:
        logger.debug("Scheduler start: %s", e)


# -----------------------
# Register handlers
# -----------------------
def register_handlers(app: Application):
    # command `/mood`
    app.add_handler(CommandHandler("mood", mood_command))
    # main menu callback
    app.add_handler(CallbackQueryHandler(cb_menu_handler, pattern=f"^{CB_PREFIX_MENU}\\|"))
    # choose mood callbacks
    app.add_handler(CallbackQueryHandler(cb_choose_mood, pattern=f"^{CB_PREFIX_ADD}\\|"))
    # confirm callbacks
    app.add_handler(CallbackQueryHandler(cb_confirm_mood, pattern=f"^{CB_PREFIX_CONFIRM}\\|"))
    # delete all
    app.add_handler(CallbackQueryHandler(cb_delete_all, pattern=f"^{CB_PREFIX_DELETE}\\|"))
