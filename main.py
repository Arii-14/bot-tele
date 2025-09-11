# main.py
import logging
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from config import TELEGRAM_API_KEY

# ==== Import semua fitur (modular) ====
# Pastikan modul-modul ini ada (agenda1, keuangan, note, mood)
import agenda1
import keuangan
import note  # quick note
import mood  # mood tracker

# Setup logging global — tampil jelas di stdout (Vercel logs)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ===== Command /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info("User %s menjalankan /start", getattr(user, "id", "unknown"))

    text = (
        f"😳 Hmphh… akhirnya master {getattr(user, 'first_name', 'teman')} datang juga…\n\n"
        "Aku Ira, pendamping jadwal dan hidupmu 😣✨\n"
        "📅 Agenda — /agenda_penting\n"
        "💰 Keuangan — /keuangan\n"
        "📍 Habit — /habit_user\n"
        "🗒️ Quick Note — /quick_note\n"
        "Klik tombol biar lebih gampang ⬇️"
    )

    keyboard = [
        [InlineKeyboardButton("📅 Agenda", callback_data="agenda_menu")],
        [InlineKeyboardButton("💰 Keuangan", callback_data="keuangan_menu")],
        [InlineKeyboardButton("📍 Habit", callback_data="habit_menu")],
        [InlineKeyboardButton("🗒️ Quick Note", callback_data="quick_note_menu")],
    ]
    # safety: if message is None (callback), fall back to answer_callback_query where appropriate
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        logger.warning("start: tidak ada update.message, mengabaikan")


# ===== small wrapper: open keuangan menu when main-menu button clicked =====
async def open_keuangan_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()
        try:
            text, markup = keuangan.build_keuangan_menu_text_and_markup()
            await q.edit_message_text(text, reply_markup=markup)
        except Exception as e:
            logger.exception("open_keuangan_menu fallback triggered: %s", e)
            try:
                await keuangan.keuangan_command(update, context)
            except Exception as ex:
                logger.exception("open_keuangan_menu: fallback kedua gagal: %s", ex)


# ===== Global error handler =====
async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception while processing an update: %s", context.error)


# ===== Startup: set command & jalankan init modul =====
async def on_startup(app):
    logger.info("Menjalankan startup semua fitur...")

    for feature in [agenda1, keuangan, note, mood]:
        if hasattr(feature, "on_startup"):
            try:
                await feature.on_startup(app)
            except Exception as e:
                logger.exception(
                    "Error running on_startup for %s: %s",
                    getattr(feature, "__name__", str(feature)),
                    e,
                )

    commands = [
        BotCommand("start", "👋 Mulai bot"),
        BotCommand("agenda_penting", "📅 Agenda kamu"),
        BotCommand("keuangan", "💰 Menu keuangan"),
        BotCommand("habit_user", "📍 Habit tracker"),
        BotCommand("quick_note", "🗒️ Quick Note"),
        BotCommand("mood", "🎭 Mood tracker"),
    ]
    try:
        await app.bot.set_my_commands(commands)
        logger.info("Set commands selesai ✅")
    except Exception as e:
        logger.warning("Gagal set commands: %s", e)


# ===== Build Application tanpa run_polling =====
try:
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_API_KEY)
        .post_init(on_startup)
        .build()
    )
    logger.info("Application object built")
except Exception:
    logger.exception("Gagal membangun Application — cek TELEGRAM_API_KEY dan dependensi")
    raise

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(note.cb_menu, pattern="^quick_note_menu$"))
application.add_handler(CallbackQueryHandler(open_keuangan_menu, pattern="^keuangan_menu$"))

try:
    if hasattr(note, "register_handlers"):
        note.register_handlers(application)
        logger.info("note handlers registered")
except Exception as e:
    logger.exception("Gagal register note handlers: %s", e)

try:
    if hasattr(mood, "register_handlers"):
        mood.register_handlers(application)
        logger.info("mood handlers registered")
except Exception as e:
    logger.exception("Gagal register mood handlers: %s", e)

for feature in [agenda1, keuangan]:
    if hasattr(feature, "register_handlers"):
        try:
            feature.register_handlers(application)
            logger.info(
                "registered handlers for %s",
                getattr(feature, "__name__", str(feature)),
            )
        except Exception as e:
            logger.exception(
                "Gagal register handlers for %s: %s",
                getattr(feature, "__name__", str(feature)),
                e,
            )

# add error handler
try:
    application.add_error_handler(_error_handler)
except Exception:
    logger.info("Cannot register app-level error handler with this PTB version (non-fatal)")

logger.info("✅ Bot Application built (tanpa polling, siap dipakai oleh wrapper HTTP)")
