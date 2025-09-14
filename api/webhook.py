import threading
import asyncio
import logging
from flask import Flask, request, jsonify, Response
from telegram import Update
from main import application  # ambil bot application dari main.py

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

_loop = asyncio.new_event_loop()

def _start_background_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

_thread = threading.Thread(target=_start_background_loop, args=(_loop,), daemon=True)
_thread.start()

@app.route("/", methods=["GET"])
def home():
    return Response("🤖 Bot is alive on Vercel!", mimetype="text/plain")

@app.route("/api/webhook", methods=["POST"])
def webhook():
    if not request.is_json:
        return jsonify({"error": "invalid content type"}), 400

    data = request.get_json(force=True)
    try:
        update = Update.de_json(data, application.bot)
        asyncio.run_coroutine_threadsafe(application.process_update(update), _loop)
    except Exception as e:
        logger.exception("Webhook error: %s", e)
        return jsonify({"error": "internal error", "detail": str(e)}), 500

    return jsonify({"status": "ok"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200
