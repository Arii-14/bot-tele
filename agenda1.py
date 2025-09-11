# bot_agenda_penting_full_fixed_namespaced.py
import asyncio
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from db import fetch_one, fetch_all, execute_query
from config import TELEGRAM_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ASK_NAMA_AGENDA, ASK_DEADLINE = range(2)

# --- Reminder templates (randomized per stage) ---
INITIAL_TEMPLATES = [
    "🔔 *Pengingat:* Agenda *{nama}*\nDeadline: `{dl}`\nMasih sekitar {hours} jam — jangan lupa cek ya, master~",
    "📣 Master, ada agenda *{nama}* yang deadline-nya `{dl}`. Sekitar {hours} jam lagi loh, siap-siap!",
    "✨ Heads up! *{nama}* deadline `{dl}` — kira-kira {hours} jam lagi. Tetap semangat, master!",
]

HOURLY_TEMPLATES = [
    "⏰ *Ingat!* Agenda *{nama}*, deadline `{dl}` — tersisa {hours} jam lagi. Ayo fokus sedikit~",
    "⌛ Waktu jalan, master! *{nama}* masih {hours} jam tersisa sampai `{dl}`. Gas dikit, ya!",
    "📢 Reminder: *{nama}* deadline `{dl}` — sekitar {hours} jam lagi. Jangan molor, master!",
]

PANIC_TEMPLATES = [
    "⚠️ *PANIK MODE!* Agenda *{nama}* tinggal {mins} menit lagi (`{dl}`)! Cepetan lakukan atau tandai selesai!",
    "🚨 Waktu mepet! *{nama}* cuma sisa {mins} menit sampai `{dl}`. Aksi sekarang, bukan nanti!",
    "🔥 Almost there: *{nama}* tinggal {mins} menit! Fokus, master—ini kudu kelar sekarang!",
]


# --- Ensure reminder table exists (idempotent) ---
def ensure_reminder_table():
    q = """
    CREATE TABLE IF NOT EXISTS agenda_reminder (
        id INT AUTO_INCREMENT PRIMARY KEY,
        agenda_id INT NOT NULL,
        last_sent TIMESTAMP NULL DEFAULT NULL,
        stage VARCHAR(30) NULL,
        UNIQUE KEY (agenda_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    execute_query(q)


# ---------- Safe reply/edit helpers ----------
async def safe_reply(update: Update, text: str, reply_markup=None, parse_mode=None):
    """Reply to message if available, else send message to chat_id."""
    if getattr(update, "message", None):
        return await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    if getattr(update, "callback_query", None) and update.callback_query.message:
        return await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id:
        bot = update.get_bot()
        return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    logger.warning("safe_reply: no target to reply to")


async def safe_edit(query, text: str, reply_markup=None, parse_mode=None):
    """Edit if message exists, else send new message."""
    if query and getattr(query, "message", None):
        try:
            return await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e:
            logger.info("safe_edit: edit failed, sending new message: %s", e)
            return await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    logger.warning("safe_edit: no query.message found")


# --- Agenda menu (send or edit) ---
async def agenda_menu_send(query):
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Agenda", callback_data="agenda_add")],
        [InlineKeyboardButton("📋 Lihat Agenda Aktif", callback_data="agenda_view")],
        [InlineKeyboardButton("📋 Lihat Semua Agenda", callback_data="agenda_view_all")],
        [InlineKeyboardButton("✅ Tandai Selesai", callback_data="agenda_mark_done")],
        [InlineKeyboardButton("❌ Batal Agenda", callback_data="agenda_mark_cancel")],
        [InlineKeyboardButton("🗑 Hapus Agenda", callback_data="agenda_delete_menu")],
        [InlineKeyboardButton("🗑 Hapus Semua Agenda", callback_data="agenda_delete_all")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await safe_edit(query, "Pilih aksi untuk Agenda Penting kamu:", reply_markup=reply_markup)


async def agenda_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Agenda", callback_data="agenda_add")],
        [InlineKeyboardButton("📋 Lihat Agenda Aktif", callback_data="agenda_view")],
        [InlineKeyboardButton("📋 Lihat Semua Agenda", callback_data="agenda_view_all")],
        [InlineKeyboardButton("✅ Tandai Selesai", callback_data="agenda_mark_done")],
        [InlineKeyboardButton("❌ Batal Agenda", callback_data="agenda_mark_cancel")],
        [InlineKeyboardButton("🗑 Hapus Agenda", callback_data="agenda_delete_menu")],
        [InlineKeyboardButton("🗑 Hapus Semua Agenda", callback_data="agenda_delete_all")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await safe_reply(update, "Pilih aksi untuk Agenda Penting kamu:", reply_markup=reply_markup)


# --- PAGINATION MODULE (10 items per page) ---
ITEMS_PER_PAGE = 10


def build_pagination_keyboard(status: str, page: int, total_pages: int):
    buttons = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"agenda_paginate_{status}_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"agenda_paginate_{status}_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="agenda_menu")])
    return InlineKeyboardMarkup(buttons)


async def handle_paginate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""

    m = re.match(r"^agenda_paginate_(?P<status>aktif|selesai|batal|terlewat)_(?P<page>\d+)$", data)
    if not m:
        logger.warning("handle_paginate: invalid callback data: %s", data)
        await safe_edit(query, "Navigasi tidak dikenali. Kembali ke menu.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="agenda_menu")]]))
        return

    status = m.group("status")
    try:
        page = int(m.group("page"))
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    rows = fetch_all("SELECT * FROM agenda_penting WHERE status=%s ORDER BY deadline ASC", (status,))
    if not rows:
        await safe_edit(query, f"Ga ada agenda dengan status *{status}* nih, master 🥺", parse_mode="Markdown")
        return

    total_pages = max(1, (len(rows) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    if page > total_pages:
        page = total_pages

    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    sliced = rows[start:end]

    text_lines = [f"📋 *Agenda dengan status {status}:* (Hal {page}/{total_pages})"]
    for ag in sliced:
        dl = ag["deadline"].strftime("%Y-%m-%d %H:%M") if ag.get("deadline") else "N/A"
        text_lines.append(
            f"- {ag['id']}. *{ag['nama_agenda']}*\n  Deadline: `{dl}`\n  Status: `{ag['status']}`"
        )

    await safe_edit(
        query,
        "\n".join(text_lines),
        parse_mode="Markdown",
        reply_markup=build_pagination_keyboard(status, page, total_pages),
    )


# --- Menu click handler ---
async def menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return None
    await query.answer()

    data = query.data or ""
    logger.info("menu_click callback data: %s", data)

    # ADD
    if data == "agenda_add":
        await safe_edit(query, "Masukin nama agenda kamu:")
        return ASK_NAMA_AGENDA

    # VIEW ACTIVE
    if data == "agenda_view":
        rows = fetch_all("SELECT * FROM agenda_penting WHERE status='aktif' ORDER BY deadline ASC")
        if not rows:
            await safe_edit(query, "Ga ada agenda aktif nih, master 🥺")
        else:
            text_lines = ["📋 *Agenda Aktif:*"]
            for ag in rows:
                dl = ag["deadline"].strftime("%Y-%m-%d %H:%M") if ag.get("deadline") else "N/A"
                text_lines.append(f"- {ag['id']}. *{ag['nama_agenda']}* (Deadline: `{dl}`)")
            await safe_edit(query, "\n".join(text_lines), parse_mode="Markdown")
        return None

    # VIEW ALL (submenu) -> now uses pagination entry callbacks
    if data == "agenda_view_all":
        keyboard = [
            [InlineKeyboardButton("📅 Aktif", callback_data="agenda_paginate_aktif_1")],
            [InlineKeyboardButton("✅ Selesai", callback_data="agenda_paginate_selesai_1")],
            [InlineKeyboardButton("❌ Batal", callback_data="agenda_paginate_batal_1")],
            [InlineKeyboardButton("⏰ Terlewat", callback_data="agenda_paginate_terlewat_1")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="agenda_menu")],
        ]
        await safe_edit(query, "Pilih status agenda yang ingin dilihat:", reply_markup=InlineKeyboardMarkup(keyboard))
        return None

    # BACK TO AGENDA MENU
    if data == "agenda_menu":
        await agenda_menu_send(query)
        return None

    # MARK DONE
    if data == "agenda_mark_done":
        rows = fetch_all("SELECT * FROM agenda_penting WHERE status='aktif' ORDER BY deadline ASC")
        if not rows:
            await safe_edit(query, "Ga ada agenda yang bisa ditandai selesai 🥺")
        else:
            keyboard = [
                [InlineKeyboardButton(f"{ag['nama_agenda']}", callback_data=f"agenda_done_{int(ag['id'])}")]
                for ag in rows
            ]
            await safe_edit(query, "Pilih agenda yang udah selesai:", reply_markup=InlineKeyboardMarkup(keyboard))
        return None

    # MARK CANCEL
    if data == "agenda_mark_cancel":
        rows = fetch_all("SELECT * FROM agenda_penting WHERE status='aktif' ORDER BY deadline ASC")
        if not rows:
            await safe_edit(query, "Ga ada agenda yang bisa dibatalin 🥺")
        else:
            keyboard = [
                [InlineKeyboardButton(f"{ag['nama_agenda']}", callback_data=f"agenda_cancel_{int(ag['id'])}")]
                for ag in rows
            ]
            await safe_edit(query, "Pilih agenda yang mau dibatalin:", reply_markup=InlineKeyboardMarkup(keyboard))
        return None

    # DELETE MENU -> show list with agenda_delete_<id>
    if data == "agenda_delete_menu":
        rows = fetch_all("SELECT * FROM agenda_penting ORDER BY deadline ASC")
        if not rows:
            await safe_edit(query, "Ga ada agenda yang bisa dihapus 🥺")
        else:
            keyboard = []
            for ag in rows:
                try:
                    aid = int(ag["id"])
                except Exception:
                    logger.warning("Non-int id in DB row: %s", ag)
                    continue
                keyboard.append(
                    [InlineKeyboardButton(f"{aid} • {ag['nama_agenda']}", callback_data=f"agenda_delete_{aid}")]
                )
            keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="agenda_menu")])
            await safe_edit(query, "Pilih agenda yang mau dihapus:", reply_markup=InlineKeyboardMarkup(keyboard))
        return None

    # DELETE ALL AGENDA (konfirmasi flow)
    if data == "agenda_delete_all":
        telegram_id = update.effective_user.id
        user = fetch_one("SELECT * FROM user WHERE telegram_id=%s", (telegram_id,))
        if not user:
            await safe_edit(query, "Error: User belum terdaftar.")
            return None
        rows = fetch_all("SELECT * FROM agenda_penting WHERE user_id=%s", (user["id"],))
        if not rows:
            await safe_edit(query, "Master sayangg 😘 data kamu ga ada ini sayang hmphh~")
            return None
        keyboard = [
            [InlineKeyboardButton("✅ Yes sayang", callback_data="agenda_confirm_delete_all_yes")],
            [InlineKeyboardButton("❌ No sayang", callback_data="agenda_confirm_delete_all_no")],
        ]
        await safe_edit(
            query,
            "Master pilih yang mana sayang aa hmpphh 😣\nYes or No sayang?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return None

    # KONFIRMASI YES / NO HAPUS SEMUA
    if data == "agenda_confirm_delete_all_yes":
        telegram_id = update.effective_user.id
        user = fetch_one("SELECT * FROM user WHERE telegram_id=%s", (telegram_id,))
        if not user:
            await safe_edit(query, "Error: User gak ketemu.")
            return None
        execute_query(
            "DELETE FROM agenda_reminder WHERE agenda_id IN (SELECT id FROM agenda_penting WHERE user_id=%s)",
            (user["id"],),
        )
        execute_query("DELETE FROM agenda_penting WHERE user_id=%s", (user["id"],))
        await safe_edit(query, "Sudah terhapus master kaya mantan master dihapus ke tong sampah hahaha 🗑😂")
        return None

    if data == "agenda_confirm_delete_all_no":
        await safe_edit(
            query,
            "Oke master sayang dibatalkan 😘 jangan kepencet lagi ya kalau master kepencet tombol itu hmphh baka!",
        )
        return None

    return None


# --- Add agenda conversation steps ---
async def add_agenda_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not getattr(update, "message", None):
        return ConversationHandler.END
    context.user_data["nama_agenda"] = update.message.text.strip()
    await safe_reply(
        update,
        "Masukin deadline agenda kamu (format: YYYY-MM-DD HH:MM) — contoh: 2025-08-11 14:30",
    )
    return ASK_DEADLINE


async def add_agenda_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not getattr(update, "message", None):
        return ConversationHandler.END
    raw = update.message.text.strip()
    nama_agenda = context.user_data.get("nama_agenda")
    telegram_id = update.effective_user.id
    user = fetch_one("SELECT * FROM user WHERE telegram_id=%s", (telegram_id,))
    if not user:
        await safe_reply(update, "Error: User belum terdaftar!")
        return ConversationHandler.END

    try:
        deadline = datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        await safe_reply(update, "Format deadline salah. Gunakan: YYYY-MM-DD HH:MM")
        return ConversationHandler.END

    execute_query(
        "INSERT INTO agenda_penting (user_id, nama_agenda, deadline, status) VALUES (%s, %s, %s, 'aktif')",
        (user["id"], nama_agenda, deadline),
    )

    last_id_row = fetch_one(
        "SELECT id FROM agenda_penting WHERE user_id=%s AND nama_agenda=%s ORDER BY id DESC LIMIT 1",
        (user["id"], nama_agenda),
    )
    if last_id_row:
        execute_query(
            "INSERT IGNORE INTO agenda_reminder (agenda_id, last_sent, stage) VALUES (%s, NULL, NULL)",
            (last_id_row["id"],),
        )

    await safe_reply(update, f"Agenda *{nama_agenda}* berhasil ditambah ✅", parse_mode="Markdown")
    return ConversationHandler.END


# --- Action handler (done / cancel / delete) with robust parsing ---
ACTION_ID_RE = re.compile(r"^agenda_(done|cancel|delete)_(\d+)$")


async def action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    logger.info("Callback data diterima: %s", query.data)
    await query.answer()

    m = ACTION_ID_RE.match(query.data or "")
    if not m:
        logger.warning("action_handler: callback data not matching action_id pattern: %s", query.data)
        await safe_edit(
            query,
            "Aksi tidak dikenali atau tombol navigasi. Kembali ke menu.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="agenda_menu")]]),
        )
        return

    action = m.group(1)
    ag_id = int(m.group(2))

    agenda = fetch_one("SELECT * FROM agenda_penting WHERE id=%s", (ag_id,))
    if not agenda:
        await safe_edit(query, f"Agenda dengan ID `{ag_id}` gak ditemukan di database.", parse_mode="Markdown")
        return

    if action == "done":
        ok = execute_query("UPDATE agenda_penting SET status='selesai' WHERE id=%s", (ag_id,))
        if ok:
            execute_query("DELETE FROM agenda_reminder WHERE agenda_id=%s", (ag_id,))
            await safe_edit(query, "Agenda udah ditandai selesai ✅")
        else:
            await safe_edit(query, "Gagal menandai selesai, coba lagi nanti.")
    elif action == "cancel":
        ok = execute_query("UPDATE agenda_penting SET status='batal' WHERE id=%s", (ag_id,))
        if ok:
            execute_query("DELETE FROM agenda_reminder WHERE agenda_id=%s", (ag_id,))
            await safe_edit(query, "Agenda dibatalin ❌")
        else:
            await safe_edit(query, "Gagal membatalkan agenda, coba lagi nanti.")
    elif action == "delete":
        ok = execute_query("DELETE FROM agenda_penting WHERE id=%s", (ag_id,))
        if ok:
            execute_query("DELETE FROM agenda_reminder WHERE agenda_id=%s", (ag_id,))
            await safe_edit(query, "Agenda dihapus 🗑")
        else:
            await safe_edit(query, "Gagal hapus agenda, coba lagi nanti.")
    else:
        await safe_edit(query, "Aksi nggak dikenali.")


# --- Reminder text builder using templates ---
def _to_dt(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(val, fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


def build_reminder_text(nama_agenda: str, deadline: datetime, time_left: timedelta, stage: str) -> str:
    seconds_left = max(0, int(time_left.total_seconds()))
    hours_left = seconds_left // 3600
    mins_left = seconds_left // 60
    dl = deadline.strftime("%Y-%m-%d %H:%M")

    if stage == "initial":
        tmpl = random.choice(INITIAL_TEMPLATES)
        return tmpl.format(nama=nama_agenda, dl=dl, hours=hours_left, mins=mins_left)
    if stage == "hourly":
        tmpl = random.choice(HOURLY_TEMPLATES)
        return tmpl.format(nama=nama_agenda, dl=dl, hours=hours_left, mins=mins_left)
    if stage == "panic":
        tmpl = random.choice(PANIC_TEMPLATES)
        return tmpl.format(nama=nama_agenda, dl=dl, hours=hours_left, mins=mins_left)
    return f"🔔 Agenda *{nama_agenda}* — Deadline: `{dl}`"


# --- Reminder loop ---
async def reminder_loop(application: Application):
    logger.info("Reminder loop started")
    while True:
        try:
            rows = fetch_all(
                """
                SELECT a.id, a.user_id, a.nama_agenda, a.deadline, u.telegram_id
                FROM agenda_penting a
                JOIN user u ON a.user_id = u.id
                WHERE a.status = 'aktif'
                """
            )
            now = datetime.now()
            for ag in rows:
                agenda_id = ag["id"]
                nama = ag["nama_agenda"]
                deadline: datetime = ag["deadline"]
                user_tid = ag["telegram_id"]

                rem = fetch_one("SELECT * FROM agenda_reminder WHERE agenda_id=%s", (agenda_id,))
                last_sent_raw = rem["last_sent"] if rem else None
                last_sent = _to_dt(last_sent_raw)
                stage = rem["stage"] if rem else None

                time_left = deadline - now

                # Deadline passed
                if time_left.total_seconds() <= 0:
                    execute_query("UPDATE agenda_penting SET status='terlewat' WHERE id=%s", (agenda_id,))
                    execute_query("DELETE FROM agenda_reminder WHERE agenda_id=%s", (agenda_id,))
                    text = (
                        f"⛔ *Waktu Habis!* Agenda *{nama}* udah lewat deadline "
                        f"(`{deadline.strftime('%Y-%m-%d %H:%M')}`) dan otomatis ditandai *terlewat*."
                    )
                    try:
                        await application.bot.send_message(chat_id=user_tid, text=text, parse_mode="Markdown")
                    except Exception as e:
                        logger.warning("Gagal kirim notifikasi terlewat: %s", e)
                    continue

                # Only start reminders if within 5 hours
                if time_left <= timedelta(hours=5):
                    desired_stage = "hourly" if time_left > timedelta(hours=1) else "panic"

                    if not last_sent:
                        text = build_reminder_text(nama, deadline, time_left, "initial")
                        try:
                            await application.bot.send_message(chat_id=user_tid, text=text, parse_mode="Markdown")
                        except Exception as e:
                            logger.warning("Gagal kirim reminder initial: %s", e)
                        execute_query(
                            "INSERT INTO agenda_reminder (agenda_id, last_sent, stage) VALUES (%s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE last_sent=%s, stage=%s",
                            (agenda_id, now, desired_stage, now, desired_stage),
                        )
                        continue

                    if desired_stage == "hourly":
                        if last_sent is None or (now - last_sent) >= timedelta(hours=1):
                            text = build_reminder_text(nama, deadline, time_left, "hourly")
                            try:
                                await application.bot.send_message(chat_id=user_tid, text=text, parse_mode="Markdown")
                            except Exception as e:
                                logger.warning("Gagal kirim reminder hourly: %s", e)
                            execute_query(
                                "UPDATE agenda_reminder SET last_sent=%s, stage=%s WHERE agenda_id=%s",
                                (now, "hourly", agenda_id),
                            )

                    elif desired_stage == "panic":
                        if last_sent is None or (now - last_sent) >= timedelta(minutes=15):
                            text = build_reminder_text(nama, deadline, time_left, "panic")
                            try:
                                await application.bot.send_message(chat_id=user_tid, text=text, parse_mode="Markdown")
                            except Exception as e:
                                logger.warning("Gagal kirim reminder panic: %s", e)
                            execute_query(
                                "UPDATE agenda_reminder SET last_sent=%s, stage=%s WHERE agenda_id=%s",
                                (now, "panic", agenda_id),
                            )

            await asyncio.sleep(60)
        except Exception as e:
            logger.exception("Error di reminder loop: %s", e)
            await asyncio.sleep(5)


# --- Bot commands on startup ---
async def set_bot_commands(application: Application):
    commands = [
        ("agenda_penting", "Menu Agenda Penting lo, bro"),
    ]
    await application.bot.set_my_commands(commands)


async def on_startup(application: Application):
    logger.info("Bot starting up (Agenda Penting)...")
    ensure_reminder_table()
    await set_bot_commands(application)
    try:
        application.create_task(reminder_loop(application))
    except Exception:
        loop = asyncio.get_event_loop()
        loop.create_task(reminder_loop(application))


# --- Register handlers (modular) ---
def register_handlers(app: Application):
    """
    Register all handlers to the provided Application instance.
    Call this from main.py: e.g. agenda.register_handlers(app)
    """
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_click, pattern="^agenda_add$")],
        states={
            ASK_NAMA_AGENDA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_agenda_name)],
            ASK_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_agenda_deadline)],
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("agenda_penting", agenda_menu))
    app.add_handler(conv_handler)

    # Action handler only for namespaced done/cancel/delete
    app.add_handler(CallbackQueryHandler(action_handler, pattern=r"^agenda_(done|cancel|delete)_\d+$"))

    # Pagination handler (tight pattern)
    app.add_handler(CallbackQueryHandler(handle_paginate, pattern=r"^agenda_paginate_(aktif|selesai|batal|terlewat)_\d+$"))

    # Menu clicks (exclude add since conv entry handles it)
    app.add_handler(
        CallbackQueryHandler(
            menu_click,
            pattern=(
                r"^(agenda_view|agenda_view_all|agenda_mark_done|agenda_mark_cancel|agenda_delete_menu|"
                r"agenda_delete_all|agenda_confirm_delete_all_yes|agenda_confirm_delete_all_no|agenda_menu)$"
            ),
        )
    )


# --- Optional: standalone main() so file can still run directly ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_API_KEY).post_init(on_startup).build()
    register_handlers(app)
    logger.info("Menjalankan bot (standalone mode)...")
    app.run_polling()
