import asyncio
import logging
from flask import Flask, request, jsonify, Response
from telegram import Update
from main import application

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.before_request
def init_bot():
    if not application._initialized:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(application.initialize())
        loop.run_until_complete(application.start())
        logger.info("🤖 Bot Application initialized & started (webhook mode)")

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
        loop = asyncio.get_event_loop()
        loop.run_until_complete(application.process_update(update))
        logger.info("✅ Update processed sukses: %s", data.get("update_id"))
    except Exception as e:
        logger.exception("❌ Webhook error: %s", e)
        return jsonify({"error": "internal error", "detail": str(e)}), 500

    return jsonify({"status": "ok"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200
