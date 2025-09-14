import threading
import asyncio
import logging
from flask import Flask, request, jsonify, Response
from telegram import Update
from main import application  # ambil bot application dari main.py

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Buat event loop terpisah
_loop = asyncio.new_event_loop()

def _start_background_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

_thread = threading.Thread(target=_start_background_loop, args=(_loop,), daemon=True)
_thread.start()

# ✅ Init bot sebelum request pertama
@app.before_first_request
def init_bot():
    if not application._initialized:
        _loop.create_task(application.initialize())
        _loop.create_task(application.start())
        logger.info("🤖 Bot Application initialized & started (webhook mode)")


@app.route("/", methods=["GET"])
def home():
    return Response("🤖 Bot is alive on Vercel!", mimetype="text/plain")


@app.route("/api/webhook", methods=["POST"])
def webhook():
    if not request.is_json:
        return jsonify({"error": "invalid content type"}), 400

    data = request.get_json(force=True)

    # Log raw update biar jelas apa yg masuk dari Telegram
    logger.info("📩 Incoming update: %s", data)

    try:
        update = Update.de_json(data, application.bot)

        future = asyncio.run_coroutine_threadsafe(application.process_update(update), _loop)

        # Tambahkan callback untuk log hasil eksekusi
        def _done_callback(f: asyncio.Future):
            try:
                f.result()
                logger.info("✅ Update processed sukses: %s", data.get("update_id"))
            except Exception as e:
                logger.exception("❌ Error waktu process_update: %s", e)

        future.add_done_callback(_done_callback)

    except Exception as e:
        logger.exception("Webhook error (gagal parse/process): %s", e)
        return jsonify({"error": "internal error", "detail": str(e)}), 500

    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200
