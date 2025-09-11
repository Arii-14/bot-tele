# note.py (fixed final)
import math
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# === DB & Utils (pakai helper) ===
from utils import now_wib, get_current_time, format_datetime
from db import fetch_all, fetch_one, execute_query

logger = logging.getLogger(__name__)

QN_PREFIX = "qn__"
MAX_NOTE_LENGTH = 1000
QN_ACTION_EXPIRE_SECONDS = 5 * 60  # 5 menit
PAGE_LIMIT = 10  # tampilkan 10 item per halaman

# In-memory fallback store
_pending_actions = {}


# ===== Helper Keyboards =====
def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 Add Note", callback_data=f"{QN_PREFIX}add")],
            [InlineKeyboardButton("🗑️ Delete One", callback_data=f"{QN_PREFIX}del1_menu:1")],
            [InlineKeyboardButton("💣 Delete All", callback_data=f"{QN_PREFIX}delall_menu")],
            [InlineKeyboardButton("📚 List Notes", callback_data=f"{QN_PREFIX}list:1")],
        ]
    )


def kb_pagination(base_tag: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    page = max(1, min(page, total_pages))
    prev_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⬅️ Prev", callback_data=f"{QN_PREFIX}{base_tag}:{prev_page}"),
                InlineKeyboardButton("🏠 Menu Utama", callback_data=f"{QN_PREFIX}menu"),
                InlineKeyboardButton("➡️ Next", callback_data=f"{QN_PREFIX}{base_tag}:{next_page}"),
            ]
        ]
    )


def kb_delete_one_page(items):
    rows = [
        [
            InlineKeyboardButton(
                f"🗑️ Hapus #{it['id']} — {it['note_text'][:30].replace(chr(10), ' ')}…",
                callback_data=f"{QN_PREFIX}del1:{it['id']}",
            )
        ]
        for it in items
    ]
    rows.append([InlineKeyboardButton("🏠 Menu Utama", callback_data=f"{QN_PREFIX}menu")])
    return InlineKeyboardMarkup(rows)


# ===== DB Helpers =====
def _count_notes(user_id: int) -> int:
    row = fetch_one("SELECT COUNT(*) AS total FROM quick_notes WHERE user_id=%s", (user_id,))
    return int(row["total"]) if row else 0


def _fetch_notes_page(user_id: int, page: int, limit: int = PAGE_LIMIT):
    offset = (page - 1) * limit
    try:
        return (
            fetch_all(
                "SELECT id, note_text, day_name, created_at "
                "FROM quick_notes WHERE user_id=%s "
                "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (user_id, limit, offset),
            )
            or []
        )
    except Exception as e:
        logger.exception("Fetch notes page error: %s", e)
        return []


def _insert_note(user_id: int, text: str) -> bool:
    now = now_wib()
    _, day_indo = get_current_time()
    try:
        return execute_query(
            "INSERT INTO quick_notes (user_id, note_text, day_name, created_at) "
            "VALUES (%s,%s,%s,%s)",
            (user_id, text, day_indo, now),
        )
    except Exception as e:
        logger.exception("Insert note error: %s", e)
        return False


def _delete_one(user_id: int, note_id: int) -> bool:
    try:
        return execute_query("DELETE FROM quick_notes WHERE id=%s AND user_id=%s", (note_id, user_id))
    except Exception as e:
        logger.exception("Delete one note error: %s", e)
        return False


def _delete_all(user_id: int) -> bool:
    try:
        return execute_query("DELETE FROM quick_notes WHERE user_id=%s", (user_id,))
    except Exception as e:
        logger.exception("Delete all notes error: %s", e)
        return False


# ===== UI Text =====
def _menu_text() -> str:
    return (
        "🗒️ **Quick Note Menu**\n\n"
        "• 📝 Add Note\n"
        "• 🗑️ Delete One\n"
        "• 💣 Delete All\n"
        "• 📚 List Notes\n"
    )


def _render_note_list_text(items, page: int, total: int) -> str:
    if total == 0:
        return "Belum ada catatan sama sekali. Coba tambah dulu di Add Note."
    total_pages = max(1, math.ceil(total / PAGE_LIMIT))
    page = max(1, min(page, total_pages))
    lines = [f"📚 Daftar Quick Notes • Halaman {page}/{total_pages} • Total {total}\n"]
    for it in items:
        created = format_datetime(it["created_at"]) if it.get("created_at") else ""
        note_text = it.get("note_text", "").strip()
        # show detail per item: id, day, created_at, full text (but trimmed visually)
        lines.append(
            f"• #{it['id']} [{it.get('day_name','-')}, {created}]\n  {note_text}"
        )
    return "\n".join(lines)


# ===== Handlers =====
async def cmd_quick_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("User %s menjalankan /quick_note", update.effective_user.id)
    await update.message.reply_text(_menu_text(), reply_markup=kb_main_menu())


async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    logger.info("User %s membuka Quick Note menu (cb_menu)", q.from_user.id)
    await q.edit_message_text(_menu_text(), reply_markup=kb_main_menu())


async def cb_add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    ts = int(time.time())
    try:
        context.user_data["qn_action"] = "add_note"
        context.user_data["qn_action_ts"] = ts
    except Exception:
        logger.warning("context.user_data not usable for user %s", uid)
    _pending_actions[uid] = {"action": "add_note", "ts": ts}
    logger.info("User %s mulai menambahkan note (flag set)", uid)
    await q.edit_message_text(f"Mau nyatat apa? Batas {MAX_NOTE_LENGTH} karakter. Ketik pesan berikutnya ya.")


async def note_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    action = context.user_data.get("qn_action") if getattr(context, "user_data", None) else None
    ts = context.user_data.get("qn_action_ts") if getattr(context, "user_data", None) else None

    if not action and uid in _pending_actions:
        record = _pending_actions.get(uid)
        if record:
            action = record.get("action")
            ts = record.get("ts")

    if action != "add_note":
        await update.message.reply_text(
            "🙏 Untuk menambah Quick Note: buka /quick_note lalu klik tombol 📝 Add Note dulu ya."
        )
        return

    now_ts = int(time.time())
    ts_int = int(ts or 0)
    if now_ts - ts_int > QN_ACTION_EXPIRE_SECONDS:
        try:
            context.user_data.pop("qn_action", None)
            context.user_data.pop("qn_action_ts", None)
        except Exception:
            pass
        _pending_actions.pop(uid, None)
        await update.message.reply_text("⏰ Waktu nulis catatan sudah habis. Coba lagi dari /quick_note ya.")
        return

    text = (update.message.text or "").strip()
    if not text or len(text) > MAX_NOTE_LENGTH:
        await update.message.reply_text("Catatan kosong atau terlalu panjang!")
        return

    ok = False
    try:
        ok = _insert_note(uid, text)
    except Exception as e:
        logger.exception("Unexpected error while inserting note: %s", e)

    if ok:
        await update.message.reply_text("✅ Catatan berhasil disimpan!")
    else:
        await update.message.reply_text("❌ Gagal nyimpan catatan! Coba lagi nanti.")

    await update.message.reply_text(_menu_text(), reply_markup=kb_main_menu())

    try:
        context.user_data.pop("qn_action", None)
        context.user_data.pop("qn_action_ts", None)
    except Exception:
        pass
    _pending_actions.pop(uid, None)


# ===== Callback routers (list, delete, dll) =====
async def cb_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
    q = update.callback_query
    await q.answer()
    total = _count_notes(q.from_user.id)
    total_pages = max(1, math.ceil(total / PAGE_LIMIT))
    page = max(1, min(page, total_pages))
    items = _fetch_notes_page(q.from_user.id, page)
    await q.edit_message_text(
        _render_note_list_text(items, page, total),
        reply_markup=kb_pagination("list", page, total_pages),
    )


async def cb_del1_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
    q = update.callback_query
    await q.answer()
    total = _count_notes(q.from_user.id)
    total_pages = max(1, math.ceil(total / PAGE_LIMIT))
    page = max(1, min(page, total_pages))
    items = _fetch_notes_page(q.from_user.id, page)
    if not items:
        await q.edit_message_text("Belum ada catatan untuk dihapus.", reply_markup=kb_main_menu())
        return
    # tampilkan list singkat dengan tombol delete langsung per item
    await q.edit_message_text("Pilih catatan yg mau dihapus:", reply_markup=kb_delete_one_page(items))


async def cb_del1_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, note_id: int):
    q = update.callback_query
    await q.answer()
    ok = _delete_one(q.from_user.id, note_id)
    await q.edit_message_text("✅ Sukses hapus!" if ok else "❌ Gagal hapus!", reply_markup=kb_main_menu())


async def cb_delall_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f"{QN_PREFIX}delall_yes"),
                InlineKeyboardButton("❌ No", callback_data=f"{QN_PREFIX}delall_no"),
            ]
        ]
    )
    await q.edit_message_text("Yakin hapus semua?", reply_markup=kb)


async def cb_delall_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ok = _delete_all(q.from_user.id)
    await q.edit_message_text("Semua catatan sudah dihapus!" if ok else "Gagal menghapus semua.", reply_markup=kb_main_menu())


async def cb_delall_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Dibatalkan. Catatan aman.", reply_markup=kb_main_menu())


# ===== Centralized callback router =====
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    await q.answer()

    if data == f"{QN_PREFIX}menu":
        return await cb_menu(update, context)
    if data == f"{QN_PREFIX}add":
        return await cb_add_note(update, context)
    if data == f"{QN_PREFIX}delall_menu":
        return await cb_delall_menu(update, context)
    if data == f"{QN_PREFIX}delall_yes":
        return await cb_delall_yes(update, context)
    if data == f"{QN_PREFIX}delall_no":
        return await cb_delall_no(update, context)
    if data.startswith(f"{QN_PREFIX}list:"):
        _, tail = data.split(":", 1)
        return await cb_list(update, context, int(tail))
    if data.startswith(f"{QN_PREFIX}del1_menu:"):
        _, tail = data.split(":", 1)
        return await cb_del1_menu(update, context, int(tail))
    if data.startswith(f"{QN_PREFIX}del1:"):
        _, tail = data.split(":", 1)
        return await cb_del1_confirm(update, context, int(tail))

    await q.edit_message_text("Aksi Quick Note tidak dikenali. Kembali ke menu.", reply_markup=kb_main_menu())


# ===== Register Handlers =====
def register_handlers(app: Application):
    app.add_handler(CommandHandler("quick_note", cmd_quick_note))

    # FIXED: corrected regex patterns (use single backslash \d+)
    strict_pattern = (
        r"^(?:"
        r"qn__menu|qn__add|"
        r"qn__list:\d+|qn__del1_menu:\d+|qn__del1:\d+|"
        r"qn__delall_menu|qn__delall_yes|qn__delall_no"
        r")$"
    )
    app.add_handler(CallbackQueryHandler(on_callback, pattern=strict_pattern))

    # 🟢 penting: kasih group=1 agar note_text_input lebih prioritas
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, note_text_input),
        group=1,
    )

    logger.info("Handler Quick Note ✅")
