# db.py
import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG

def get_connection():
    """Bikin koneksi ke database."""
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            ssl_ca=DB_CONFIG["ssl_ca"],
            ssl_verify_cert=DB_CONFIG["ssl_verify_cert"]
        )
        return conn
    except Error as e:
        print(f"[DB ERROR] Gagal konek ke DB: {e}")
        return None

def fetch_all(query, params=None):
    """Ambil banyak data dari DB."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        result = cursor.fetchall()
        return result
    except Error as e:
        print(f"[DB ERROR] Query gagal: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def fetch_one(query, params=None):
    """Ambil satu data dari DB."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        result = cursor.fetchone()
        return result
    except Error as e:
        print(f"[DB ERROR] Query gagal: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def execute_query(query, params=None):
    """Jalankan INSERT/UPDATE/DELETE ke DB."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        conn.commit()
        return True
    except Error as e:
        print(f"[DB ERROR] Query gagal: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()
