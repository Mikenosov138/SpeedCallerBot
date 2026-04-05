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

📱 *Numbers MUST start with +* (11-13 chars total)

👆 Press 📞 *Call* to start!"""
    
    markup = get_main_markup()
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')
    logger.info(f"User {user_id} started bot")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
    if call.data == "call":
        total = get_user_stats(user_id)
        phone_result = get_next_phone(user_id)
        
        if phone_result and total > 0:
            phone = phone_result[0]
            text = f"""🚀 *Welcome to SpeedCaller Bot!*
💪 *Make speed calls*

📊 *Client:* `1/{total}`
📱 *Number:* `{phone}`"""
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(InlineKeyboardButton("📞 *CALL NOW*", url=f"tel:{phone}"))
            markup.add(InlineKeyboardButton("➡️ Skip", callback_data="skip"))
            markup.add(InlineKeyboardButton("↩️ Back", callback_data="back"))
            
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')
        else:
            markup = get_main_markup()
            bot.send_message(chat_id, f"📭 *No numbers* ({total})\nUpload database first!", 
                           reply_markup=markup, parse_mode='Markdown')
    
    elif call.data == "skip":
        delete_oldest_phone(user_id)
        total = get_user_stats(user_id)
        markup = get_main_markup()
        bot.send_message(chat_id, f"✅ *Skipped!*\n📊 *Remaining:* `{total}`", 
                        reply_markup=markup, parse_mode='Markdown')
    
    elif call.data == "back":
        markup = get_main_markup()
        bot.send_message(chat_id, "↩️ *Back to menu*", reply_markup=markup, parse_mode='Markdown')
    
    elif call.data == "settings":
        markup = InlineKeyboardMarkup(row_width=1)
        markup
