import threading
import asyncio
import logging
from flask import Flask, request, jsonify, Response
from telegram import Update
from main import application  # ambil bot application dari main.py

# === Setup logging ===
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# === Flask app (wajib variable "app" buat Vercel) ===
app = Flask(__name__)

# === Background asyncio loop ===
_loop = asyncio.new_event_loop()

def _start_background_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

_thread = threading.Thread(target=_start_background_loop, args=(_loop,), daemon=True)
_thread.start()
logger.info("Background asyncio loop started")

# === Routes ===

@app.route("/", methods=["GET"])
def home():
    return Response("🤖 Bot is alive on Vercel!", mimetype="text/plain")

@app.route("/webhook", methods=["POST"])
def webhook():
    if not request.is_json:
        logger.warning("Received non-JSON request to /webhook")
        return jsonify({"error": "invalid content type, expecting application/json"}), 400

    try:
        # Ambil update dari Telegram
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)

        # Proses update di background event loop
        asyncio.run_coroutine_threadsafe(
            application.process_update(update), _loop
        )

        logger.info("Update processed: %s", data)

        # WAJIB: balikin respon cepat biar Telegram ga timeout
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.exception("Error handling webhook: %s", e)
        return jsonify({"error": str(e)}), 500
