# ===== utils.py =====
from datetime import datetime, timedelta
import pytz

# Zona waktu Indonesia (WIB)
WIB = pytz.timezone("Asia/Jakarta")

def now_wib():
    """Dapetin waktu sekarang di WIB."""
    return datetime.now(WIB)

def get_current_time():
    """Balikin datetime sekarang + nama hari (dalam bahasa Indonesia)."""
    now = now_wib()
    day_name = now.strftime("%A")  # ex: Monday
    hari_indo = {
        "Monday": "Senin",
        "Tuesday": "Selasa",
        "Wednesday": "Rabu",
        "Thursday": "Kamis",
        "Friday": "Jumat",
        "Saturday": "Sabtu",
        "Sunday": "Minggu",
    }
    return now, hari_indo.get(day_name, day_name)

def format_tanggal(tanggal):
    """Format datetime.date ke string Indonesia."""
    bulan_indo = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    return f"{tanggal.day} {bulan_indo[tanggal.month - 1]} {tanggal.year}"

def format_waktu(waktu):
    """Format datetime.time ke HH:MM WIB."""
    return waktu.strftime("%H:%M")

def format_datetime(dt_obj):
    """Format datetime lengkap (tanggal + jam) ke bahasa Indonesia (cross-platform)."""
    if isinstance(dt_obj, datetime):
        bulan_indo = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"
        ]
        try:
            # Unix/Linux biasanya support %-d (tanpa leading zero)
            return dt_obj.strftime(f"%-d {bulan_indo[dt_obj.month - 1]} %Y %H:%M")
        except ValueError:
            # Windows tidak support %-d → fallback manual
            return f"{int(dt_obj.strftime('%d'))} {bulan_indo[dt_obj.month - 1]} {dt_obj.year} {dt_obj.strftime('%H:%M')}"
    return str(dt_obj)

def parse_int_safe(value, default=0):
    """Konversi nilai ke int, fallback ke default kalau gagal."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def jam_menit_detik(delta_seconds):
    """Konversi detik ke format X jam Y menit Z detik."""
    jam = delta_seconds // 3600
    menit = (delta_seconds % 3600) // 60
    detik = delta_seconds % 60
    return f"{jam} jam {menit} menit {detik} detik"

def tambah_jam(waktu_awal, jam):
    """Tambah jam ke waktu_awal (datetime)."""
    return waktu_awal + timedelta(hours=jam)

def kurang_jam(waktu_awal, jam):
    """Kurang jam dari waktu_awal (datetime)."""
    return waktu_awal - timedelta(hours=jam)
