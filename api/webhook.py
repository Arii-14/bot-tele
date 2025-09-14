# webhook.py
import asyncio
import logging
from flask import Flask, request, jsonify, Response
from telegram import Update
from main import application

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

async def ensure_ready():
    if not application._initialized:
        await application.initialize()
        await application.start()
        logger.info("🤖 Application initialized & started")

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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ensure_ready())

        update = Update.de_json(data, application.bot)
        loop.run_until_complete(application.process_update(update))
        logger.info("✅ Update processed sukses: %s", data.get("update_id"))

    except Exception as e:
        logger.exception("❌ Webhook error: %s", e)
        return jsonify({"error": "internal error", "detail": str(e)}), 500
    finally:
        loop.close()

    return jsonify({"status": "ok"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200
