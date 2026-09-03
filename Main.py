"""⚽ ایجنت بازی‌های نابرابر فوتبال - نسخه تک‌فایل"""
import httpx
import json
import os
from datetime import datetime, timedelta, timezone

# ─────────── تنظیمات ───────────
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE = "state.json"
DAYS_AHEAD = 5
MIN_PLAYED = 5           # حداقل بازی برای اعتماد به جدول فعلی
MISMATCH_THRESHOLD = 45  # آستانه هشدار
HOME_ADVANTAGE = 8

LEAGUES = {
    "eng.1": "🏴 لیگ برتر انگلیس",
    "esp.1": "🇪🇸 لالیگا",
    "ger.1": "🇩🇪 بوندس‌لیگا",
    "ita.1": "🇮🇹 سری آ",
    "fra.1": "🇫🇷 لیگ ۱ فرانسه",
}

# رتبه‌های فصل قبل (وقتی داده فصل جاری کمه، اینا مبنا قرار می‌گیرن)
LAST_SEASON = {
