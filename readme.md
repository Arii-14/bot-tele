# 🤖 BotReminder

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Made with Love](https://img.shields.io/badge/Made%20with-❤️-red.svg)](#)

> "Karena manusia suka lupa, mari serahkan semuanya ke bot."

Bot ini dibuat untuk membantu mengatur hidup lewat **Telegram**. Mulai dari catatan agenda, keuangan, mood harian, sampai notes random, semua bisa dicatat rapi dan dikirim langsung lewat bot.

---

## ✨ Fitur

* 📅 **Reminder Agenda** → biar ga ada meeting atau deadline kelewat
* 💸 **Catatan Keuangan** → track pengeluaran biar dompet ga jebol
* 😃 **Mood Tracker** → supaya tahu kapan waktunya healing
* 📝 **Notes** → catatan random yang penting atau ga penting pun bisa
* 🔔 **Auto Notif Telegram** → biar ga perlu buka aplikasi tambahan

---

## 🛠️ Tech Stack

* 🐍 Python 3.10+
* 📬 [python-telegram-bot](https://python-telegram-bot.org/)
* ⏰ [APScheduler](https://apscheduler.readthedocs.io/)
* 🛢️ [MySQL Connector](https://pypi.org/project/mysql-connector-python/)
* ⚡ [httpx](https://www.python-httpx.org/)
* 🗂️ [python-dotenv](https://pypi.org/project/python-dotenv/)

---

## 📦 Instalasi

1. Clone repo ini:

   ```bash
   git clone https://github.com/username/BotReminder.git
   cd BotReminder
   ```

2. Buat virtual environment (opsional tapi direkomendasikan):

   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/Mac
   venv\Scripts\activate      # Windows
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

---

## ⚙️ Konfigurasi

Bikin file `.env` di root project dengan isi seperti ini:

```env
TELEGRAM_TOKEN=isi_token_bot_lu
DB_HOST=localhost
DB_USER=root
DB_PASS=password
DB_NAME=botreminder_db
```

---

## 🚀 Menjalankan Project

Jalankan bot dengan:

```bash
python main.py
```

Kalau semua benar, bot bakal langsung aktif di Telegram.

---

## 📂 Struktur Project

```
BotReminder/
│── agenda1.py       # Modul reminder agenda
│── keuangan.py      # Modul catatan keuangan
│── mood.py          # Modul mood tracker
│── note.py          # Modul catatan umum
│── db.py            # Koneksi database
│── utils.py         # Helper/utility function
│── main.py          # Entry point bot
│── config.py        # Config tambahan
│── requirements.txt # Daftar dependency
│── .env             # File konfigurasi (jangan dishare!)
│── venv/            # Virtual environment
```

---


## 🤝 Contributing

* Pull request terbuka lebar 🚪
* Bug report boleh banget 🐞
* Jangan lupa test dulu sebelum push 😅

---

## 🐱 Author

Made with ❤️ by TendouAriisu (Ari)
⭐ Kalau bermanfaat, jangan lupa kasih **star** di repo ini ya!
