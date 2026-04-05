import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import openpyxl
import sqlite3
import os
import re
import logging
from datetime import datetime

# # Logging for monitoring
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# # Secure token
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    logger.error("❌ BOT_TOKEN missing!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
logger.info("🚀 SpeedCaller Bot initialized")

# # Database with timestamps
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS numbers 
                  (phone TEXT PRIMARY KEY, user_id INTEGER, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

def clean_phone(phone_str):
    """Validate: + followed by 10-12 digits (11-14 total chars)"""
    cleaned = re.sub(r'[^\+0-9]', '', str(phone_str).strip())
    if cleaned.startswith('+') and 11 <= len(cleaned) <= 14:
        return cleaned
    return None

def get_user_stats(user_id):
    """Total numbers for user"""
    cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,))
    return cursor.fetchone()[0]

def get_next_phone(user_id):
    """Get first available phone"""
    cursor.execute("SELECT phone FROM numbers WHERE user_id=? ORDER BY rowid ASC LIMIT 1", (user_id,))
    return cursor.fetchone()

def delete_oldest_phone(user_id):
    """Skip: delete first phone"""
    cursor.execute("DELETE FROM numbers WHERE user_id=? ORDER BY rowid ASC LIMIT 1", (user_id,))
    conn.commit()

def clear_user_db(user_id):
    """Clear all user numbers"""
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
    
    # # Clean chat history (last 3 messages)
    try:
        for i in range(3):
            try:
                bot.delete_message(chat_id, message.message_id - i)
            except:
                pass
    except:
        pass
    
    text = """🚀 *Welcome to SpeedCaller Bot!* 🤝🏻

💪 *Fast phone dialing* + *duplicate protection*
✅ *COMPLETELY FREE!*

📥 *Upload database* (.xlsx **OR** text):
