from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# DB Config
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "ssl_ca": os.path.join(BASE_DIR, os.getenv("SSL_CA_PATH", "")),  # absolute path
    "ssl_verify_cert": True,
}

TELEGRAM_API_KEY = os.getenv("TELEGRAM_API_KEY", "").strip()
