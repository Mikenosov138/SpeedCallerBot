import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import openpyxl
import sqlite3
import os
import re
import logging
import time

# # Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# # Secure token
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    logger.error("❌ BOT_TOKEN missing!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
logger.info("🚀 SpeedCaller Bot initialized")

# # Database
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS numbers 
                  (phone TEXT PRIMARY KEY, user_id INTEGER, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

def clean_phone(phone_str):
    cleaned = re.sub(r'[^\+0-9]', '', str(phone_str).strip())
    if cleaned.startswith('+') and 11 <= len(cleaned) <= 14:
        return cleaned
    return None

def get_user_stats(user_id):
    cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,))
    return cursor.fetchone()[0]

def get_next_phone(user_id):
    cursor.execute("SELECT phone FROM numbers WHERE user_id=? ORDER BY rowid ASC LIMIT 1", (user_id,))
    return cursor.fetchone()

def delete_oldest_phone(user_id):
    cursor.execute("DELETE FROM numbers WHERE user_id=? ORDER BY rowid ASC LIMIT 1", (user_id,))
    conn.commit()

def clear_user_db(user_id):
    cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
    conn.commit()

def get_main_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📞 Call", callback_data="call"))
    markup.add(InlineKeyboardButton("➡️ Skip", callback_data="skip"))
    markup.add(InlineKeyboardButton("⚙️ Settings", callback_data="settings"))
    return markup

@bot.message_handler(commands=['start', 'help'])
def start_handler(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    text = """🚀 *Welcome to SpeedCaller Bot!* 🤝🏻

💪 *Fast phone dialing* + *duplicate protection*
✅ *COMPLETELY FREE!*

📥 *Upload database* (.xlsx **OR** text):
