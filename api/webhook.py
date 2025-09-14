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

# --- Global event loop ---
_loop = asyncio.new_event_loop()

def _start_background_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

_thread = threading.Thread(target=_start_background_loop, args=(_loop,), daemon=True)
_thread.start()

# --- Pastikan application di-init sekali ---
init_future = asyncio.run_coroutine_threadsafe(application.initialize(), _loop)
init_future.result()  # tunggu selesai
logger.info("✅ Application initialized di webhook.py")


@app.route("/", methods=["GET"])
def home():
    return Response("🤖 Bot is alive on Vercel!", mimetype="text/plain")


@app.route("/api/webhook", methods=["POST"])
def webhook():
    if not request.is_json:
        return jsonify({"error": "invalid content type"}), 400

    data = request.get_json(force=True)
    logger.info("📩 Incoming update: %s", data)

    try:
        update = Update.de_json(data, application.bot)
        future = asyncio.run_coroutine_threadsafe(application.process_update(update), _loop)

        def _done_callback(f: asyncio.Future):
            try:
                f.result()
                logger.info("✅ Update processed sukses: %s", data.get("update_id"))
            except Exception as e:
                logger.exception("❌ Error waktu process_update: %s", e)

        future.add_done_callback(_done_callback)

    except Exception as e:
        logger.exception("❌ Webhook error: %s", e)
        return jsonify({"error": "internal error", "detail": str(e)}), 500

    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200
