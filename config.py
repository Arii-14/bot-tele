# config.py
from dotenv import load_dotenv
import os

load_dotenv()

# DB Config
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "ssl_ca": os.getenv("SSL_CA_PATH"),
    "ssl_verify_cert": True,
}

# Token Telegram (auto-strip biar ga ada spasi/newline)
TELEGRAM_API_KEY = os.getenv("TELEGRAM_API_KEY", "").strip()
