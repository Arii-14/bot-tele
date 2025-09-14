import logging
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from config import TELEGRAM_API_KEY

import agenda1
import keuangan
import note
import mood

# Setup logging
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
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        logger.warning("start: tidak ada update.message, mengabaikan")


# ===== Debug: log semua update masuk =====
async def debug_logger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("📩 Update masuk: %s", update.to_dict())


# ===== Global error handler =====
async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception: %s", context.error)


# ===== Startup =====
async def on_startup(app):
    logger.info("🚀 Menjalankan startup semua fitur...")

    for feature in [agenda1, keuangan, note, mood]:
        if hasattr(feature, "on_startup"):
            try:
                await feature.on_startup(app)
                logger.info("✅ on_startup %s sukses", feature.__name__)
            except Exception as e:
                logger.exception("❌ on_startup gagal %s: %s", feature.__name__, e)

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
        logger.info("✅ Commands berhasil diset")
    except Exception as e:
        logger.warning("⚠️ Gagal set commands: %s", e)


# ===== Build Application =====
application = (
    ApplicationBuilder()
    .token(TELEGRAM_API_KEY)
    .post_init(on_startup)
    .build()
)
logger.info("Application object built")


# ===== Register handlers =====
application.add_handler(CommandHandler("start", start))
logger.info("Handler /start registered")

application.add_handler(CallbackQueryHandler(note.cb_menu, pattern="^quick_note_menu$"))
logger.info("Handler quick_note_menu registered")

application.add_handler(CallbackQueryHandler(lambda u, c: keuangan.keuangan_command(u, c), pattern="^keuangan_menu$"))
logger.info("Handler keuangan_menu registered")

# register external handlers
for feature in [note, mood, agenda1, keuangan]:
    if hasattr(feature, "register_handlers"):
        try:
            feature.register_handlers(application)
            logger.info("✅ Handlers registered for %s", feature.__name__)
        except Exception as e:
            logger.exception("❌ Gagal register handlers %s: %s", feature.__name__, e)

# debug handler paling akhir → log semua update yg tidak ketangkep
application.add_handler(MessageHandler(filters.ALL, debug_logger))
logger.info("Debug logger handler registered")

# add error handler
application.add_error_handler(_error_handler)

logger.info("✅ Bot Application built (tanpa polling, siap webhook)")
