# ===== keuangan_fixed.py =====
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from db import execute_query, fetch_one, fetch_all
import re
import math
import time

# ===== Konfigurasi =====
PAGE_SIZE = 10
CALLBACK_PREFIX = "keu:"  # prefix unik supaya gak bentrok dengan callback lain
# berapa detik action user valid (5 menit)
KEU_ACTION_EXPIRE_SECONDS = 5 * 60

# ===== Format Rupiah =====
def format_rp(nominal):
    try:
        return f"Rp {int(nominal):,}".replace(",", ".")
    except Exception:
        return f"Rp {nominal}"

# ===== Bikin tampilan menu utama =====
def build_keuangan_menu_text_and_markup():
    text = "Pilih menu keuangan kamu master 🥺:"
    keyboard = [
        [InlineKeyboardButton("💰 Tambah Isi Tabungan", callback_data=CALLBACK_PREFIX + "tambah_tabungan")],
        [InlineKeyboardButton("🛒 Pakai Tabungan", callback_data=CALLBACK_PREFIX + "pakai_tabungan")],
        [InlineKeyboardButton("📝 Pengeluaran Sehari-hari", callback_data=CALLBACK_PREFIX + "pengeluaran")],
        [InlineKeyboardButton("📜 List History & Ringkasan", callback_data=CALLBACK_PREFIX + "list_history")],
        [InlineKeyboardButton("❌ Delete All Data", callback_data=CALLBACK_PREFIX + "delete_all")],
    ]
    return text, InlineKeyboardMarkup(keyboard)

# ===== FETCH history (paginated) dari DB =====
def get_history_count():
    q = """
    SELECT COUNT(*) as cnt FROM (
        SELECT id, tanggal FROM tabungan
        UNION ALL
        SELECT id, tanggal FROM pakai_tabungan
        UNION ALL
        SELECT id, tanggal FROM pengeluaran
    ) t
    """
    row = fetch_one(q)
    return int(row["cnt"] or 0)

def get_history_page(page, per_page=PAGE_SIZE):
    offset = (page - 1) * per_page
    q = f"""
    SELECT * FROM (
        SELECT 'Tabungan' AS jenis, id, tanggal, nominal, keterangan as note
        FROM tabungan
        UNION ALL
        SELECT 'PakaiTabungan' AS jenis, id, tanggal, nominal, keterangan as note
        FROM pakai_tabungan
        UNION ALL
        SELECT 'Pengeluaran' AS jenis, id, tanggal, nominal, CONCAT(kategori, ': ', deskripsi) as note
        FROM pengeluaran
    ) u
    ORDER BY tanggal DESC
    LIMIT %s OFFSET %s
    """
    rows = fetch_all(q, (per_page, offset))
    return rows or []

# ===== Ringkasan & 5 data terakhir =====
def get_summary_and_last5():
    total_tabungan = fetch_one("SELECT SUM(nominal) as total FROM tabungan")["total"] or 0
    total_pakai = fetch_one("SELECT SUM(nominal) as total FROM pakai_tabungan")["total"] or 0
    total_pengeluaran = fetch_one("SELECT SUM(nominal) as total FROM pengeluaran")["total"] or 0
    sisa_tabungan = total_tabungan - total_pakai

    # ambil 5 data terakhir
    last_tabungan = fetch_all("SELECT tanggal, nominal, keterangan FROM tabungan ORDER BY tanggal DESC LIMIT 5") or []
    last_pakai = fetch_all("SELECT tanggal, nominal, keterangan FROM pakai_tabungan ORDER BY tanggal DESC LIMIT 5") or []
    last_pengeluaran = fetch_all("SELECT tanggal, kategori, deskripsi, nominal FROM pengeluaran ORDER BY tanggal DESC LIMIT 5") or []

    text = (
        f"📊 **Ringkasan Keuangan Master**\n\n"
        f"💰 Total Tabungan: {format_rp(total_tabungan)}\n"
        f"🛒 Total Dipakai: {format_rp(total_pakai)}\n"
        f"🎯 Sisa Tabungan: {format_rp(sisa_tabungan)}\n"
        f"📝 Total Pengeluaran: {format_rp(total_pengeluaran)}\n\n"
        f"📌 5 Data Terakhir:\n\n"
    )

    if last_tabungan:
        text += "💰 Nabung:\n" + "\n".join([f"- {r['tanggal']} | {format_rp(r['nominal'])} ({r.get('keterangan','')})" for r in last_tabungan]) + "\n\n"
    if last_pakai:
        text += "🛒 Pakai Tabungan:\n" + "\n".join([f"- {r['tanggal']} | {format_rp(r['nominal'])} ({r.get('keterangan','')})" for r in last_pakai]) + "\n\n"
    if last_pengeluaran:
        text += "📝 Pengeluaran:\n" + "\n".join([f"- {r['tanggal']} | {format_rp(r['nominal'])} ({r.get('kategori','')}:{r.get('deskripsi','')})" for r in last_pengeluaran]) + "\n\n"

    return text.strip()

# ===== Command /keuangan =====
async def keuangan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, reply_markup = build_keuangan_menu_text_and_markup()
    await update.message.reply_text(text, reply_markup=reply_markup)

# ===== Callback Handler (strict routing) =====
VALID_ACTIONS = {"tambah_tabungan", "pakai_tabungan", "pengeluaran", "list_history", "delete_all"}

async def keuangan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = (query.data or "")

    # quick validate prefix first
    if not data.startswith(CALLBACK_PREFIX):
        return

    payload = data[len(CALLBACK_PREFIX):]

    # exact matches
    if payload in VALID_ACTIONS:
        # set action + expiry timestamp so MessageHandler only responds to valid actions
        now_ts = int(time.time())
        if payload == "tambah_tabungan":
            await query.message.edit_text("Berapa master mau nabung? Contoh: 5000")
            context.user_data["keu_action"] = "tambah_tabungan"
            context.user_data["keu_action_ts"] = now_ts
            return

        if payload == "pakai_tabungan":
            await query.message.edit_text("Mau pakai berapa dan buat apa master? Contoh: 2000 beli snack")
            context.user_data["keu_action"] = "pakai_tabungan"
            context.user_data["keu_action_ts"] = now_ts
            return

        if payload == "pengeluaran":
            await query.message.edit_text(
                "Catat pengeluaran master 🥺! Format: kategori:deskripsi nominal. Contoh: makanan:nasi goreng 20000"
            )
            context.user_data["keu_action"] = "pengeluaran"
            context.user_data["keu_action_ts"] = now_ts
            return

        if payload == "delete_all":
            # delete everything (keputusan design: keep immediate delete, but safe via strict callback)
            execute_query("DELETE FROM tabungan;")
            execute_query("DELETE FROM pengeluaran;")
            execute_query("DELETE FROM pakai_tabungan;")
            text, reply_markup = build_keuangan_menu_text_and_markup()
            await query.message.edit_text("Udah terhapus semua master! Mari mulai data keuangan baru 🥹❤️\n\n" + text,
                                          reply_markup=reply_markup)
            context.user_data.pop("keu_action", None)
            context.user_data.pop("keu_action_ts", None)
            return

        if payload == "list_history":
            # show summary + first page (we support optional pagination below)
            summary = get_summary_and_last5()
            await query.message.edit_text(summary, parse_mode="Markdown")
            context.user_data.pop("keu_action", None)
            context.user_data.pop("keu_action_ts", None)
            return

    # support paginated list: keu:list:<page>
    if payload.startswith("list:"):
        try:
            _, page_str = payload.split(":", 1)
            page = int(page_str)
        except Exception:
            page = 1
        rows = get_history_page(page)
        total = get_history_count()
        total_pages = max(1, math.ceil(total / PAGE_SIZE))
        # build text
        if not rows:
            await query.message.edit_text("Belum ada riwayat transaksi.")
            return
        lines = [f"📜 Riwayat — Halaman {page}/{total_pages}\n"]
        for r in rows:
            jenis = r.get("jenis", "")
            tgl = r.get("tanggal", "")
            nominal = format_rp(r.get("nominal", 0) or 0)
            note = r.get("note", "")
            lines.append(f"- [{jenis}] {tgl} | {nominal} — {note}")
        # simple pagination keyboard
        kb = []
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=CALLBACK_PREFIX + f"list:{page-1}"))
        nav.append(InlineKeyboardButton("🏠 Menu Utama", callback_data=CALLBACK_PREFIX + "list_history"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("➡️ Next", callback_data=CALLBACK_PREFIX + f"list:{page+1}"))
        kb.append(nav)
        await query.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
        return

    # unknown/unsafe payload -> ignore but politely inform
    try:
        await query.message.reply_text("Terjadi sesuatu yang tak terduga — coba lagi ya master 🥺")
    except Exception:
        pass

# ===== Handler Input User (text) =====
async def keuangan_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only handle if an action is set and not expired
    action = context.user_data.get("keu_action")
    ts = context.user_data.get("keu_action_ts", 0)
    if not action:
        return  # safety: jangan ganggu fitur lain

    now_ts = int(time.time())
    if now_ts - int(ts) > KEU_ACTION_EXPIRE_SECONDS:
        # expired
        context.user_data.pop("keu_action", None)
        context.user_data.pop("keu_action_ts", None)
        try:
            await update.message.reply_text("Input keuangan kedaluwarsa. Silakan buka menu /keuangan lagi.")
        except Exception:
            pass
        return

    text = (update.message.text or "").strip()

    if action == "tambah_tabungan":
        try:
            nominal = int(re.sub(r"[^\d\-]", "", text))  # allow thousand separators but strip non-digits
            execute_query(
                "INSERT INTO tabungan (tanggal, nominal, keterangan) VALUES (NOW(), %s, %s)",
                (nominal, "Nabung bebas")
            )
            await update.message.reply_text(f"Horeee master menabung {format_rp(nominal)} bijak banget 🥺❤️")
        except Exception:
            await update.message.reply_text("Format salah master, coba angka aja ya 🥹")

    elif action == "pakai_tabungan":
        try:
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                raise ValueError("Format salah")
            nominal = int(re.sub(r"[^\d\-]", "", parts[0]))
            keterangan = parts[1].strip()
            total_tabungan = fetch_one("SELECT SUM(nominal) as total FROM tabungan")["total"] or 0
            total_pakai = fetch_one("SELECT SUM(nominal) as total FROM pakai_tabungan")["total"] or 0
            sisa_tabungan = total_tabungan - total_pakai

            if nominal > sisa_tabungan:
                await update.message.reply_text(f"Tidak ada isi tabungan yang cukup master 🥺, sisa: {format_rp(sisa_tabungan)}")
            else:
                execute_query(
                    "INSERT INTO pakai_tabungan (tanggal, nominal, keterangan) VALUES (NOW(), %s, %s)",
                    (nominal, keterangan)
                )
                await update.message.reply_text(f"Hmmphh master, {format_rp(nominal)} dipakai untuk {keterangan} 😎")
        except Exception:
            await update.message.reply_text("Format salah master, contoh: 2000 beli snack 🥺")

    elif action == "pengeluaran":
        try:
            # split last token as nominal
            kategori_deskripsi, nominal_str = text.rsplit(maxsplit=1)
            if ":" not in kategori_deskripsi:
                raise ValueError("Format kategori:deskripsi salah")
            kategori, deskripsi = kategori_deskripsi.split(":", 1)
            nominal = int(re.sub(r"[^\d\-]", "", nominal_str))
            execute_query(
                "INSERT INTO pengeluaran (tanggal, kategori, deskripsi, nominal) VALUES (NOW(), %s, %s, %s)",
                (kategori.strip(), deskripsi.strip(), nominal)
            )
            await update.message.reply_text(f"Terimakasih master, pengeluaran '{deskripsi.strip()}' sebesar {format_rp(nominal)} tercatat 😎")
        except Exception:
            await update.message.reply_text("Format salah master, contoh: makanan:nasi goreng 20000 🥺")

    # clear action after processing
    context.user_data.pop("keu_action", None)
    context.user_data.pop("keu_action_ts", None)

# ===== Daftar Handler (register ke application) =====
def register_handlers(app):
    app.add_handler(CommandHandler("keuangan", keuangan_command))

    # Build strict callback regex so it only matches keuangan callbacks we expect.
    # This avoids greedy matching of other modules that might reuse similar prefixes.
    strict_pattern = re.compile(
        r"^(?:"
        r"keu:tambah_tabungan|keu:pakai_tabungan|keu:pengeluaran|keu:list_history|keu:delete_all|"
        r"keu:list:\d+"
        r")$"
    )

    app.add_handler(CallbackQueryHandler(keuangan_callback, pattern=strict_pattern))

    # MessageHandler stays general, but keuangan_text_input verifies keu_action + timeout,
    # so it won't accidentally process messages intended for other modules.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, keuangan_text_input))

