import os
import re
import sqlite3
import logging
import time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import openpyxl
import tempfile
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect("speedcaller_v4.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    phone TEXT UNIQUE,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

user_state = {}
last_messages = {}

WELCOME_TEXT = """
👋 **Hello! SpeedCallerBot v4**

📞 **Fast client database calling**

**To maximize daily calls:**
• Load Excel or send text numbers
• Tap phone number → CALL opens
• SKIP → next number instantly
• BACK → previous number

**No limits on numbers!**
Ready? Tap ➕ 👇
"""

def delete_last_message(chat_id):
    if chat_id in last_messages:
        try:
            bot.delete_message(chat_id, last_messages[chat_id])
        except:
            pass

def main_menu_keyboard():
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("➕ Load Numbers", callback_data="load_menu"))
    return kb

@bot.message_handler(commands=['start'])
def start_handler(message):
    delete_last_message(message.chat.id)
    sent = bot.send_message(message.chat.id, WELCOME_TEXT, reply_markup=main_menu_keyboard(), parse_mode='Markdown')
    last_messages[message.chat.id] = sent.message_id

def normalize_phone(phone):
    clean = re.sub(r'[^\d+]', '', str(phone))
    if len(clean) < 8: return None
    if clean.startswith('8') and len(clean) == 11:
        clean = '7' + clean[1:]
    if not clean.startswith('+'):
        clean = '+' + clean
    return clean[-15:]

def import_numbers(user_id, data, source="manual"):
    count_added = 0
    numbers = []
    
    if source == "excel":
        try:
            wb = openpyxl.load_workbook(data)
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        if cell: numbers.append(str(cell))
        except: return 0
    else:
        numbers = [line.strip() for line in data.split('\n') if line.strip()]
    
    for phone in numbers:
        norm_phone = normalize_phone(phone)
        if norm_phone:
            try:
                cursor.execute("INSERT OR IGNORE INTO numbers (user_id, phone) VALUES (?, ?)", (user_id, norm_phone))
                if cursor.rowcount > 0: count_added += 1
            except: pass
    conn.commit()
    return count_added

def get_user_numbers(user_id):
    cursor.execute("SELECT id, phone FROM numbers WHERE user_id=? AND status='pending' ORDER BY created_at ASC", (user_id,))
    return cursor.fetchall()

def get_current_number(user_id):
    if user_id not in user_state: user_state[user_id] = {'index': 0}
    numbers = get_user_numbers(user_id)
    if not numbers: return None, None, 0
    index = user_state[user_id]['index']
    if index >= len(numbers): 
        user_state[user_id]['index'] = 0
        index = 0
    return numbers[index], index, len(numbers)

def send_current_number(chat_id, user_id):
    delete_last_message(chat_id)
    number_data, index, total = get_current_number(user_id)
    if not number_data:
        sent = bot.send_message(chat_id, "📭 **Numbers finished!**\n\nTap ➕ to load more", reply_markup=main_menu_keyboard(), parse_mode='Markdown')
    else:
        num_id, phone = number_data
        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("📞 CALL", callback_data=f"call_{num_id}"))
        kb.row(InlineKeyboardButton("⏭️ SKIP", callback_data="skip"), InlineKeyboardButton("⬅️ BACK", callback_data="back"))
        kb.row(InlineKeyboardButton(f"📊 {index+1}/{total}", callback_data="stats"))
        phone_display = phone.replace('+', '＋')
        text = f"**📱 {phone_display}**\n\n**Progress:** `{index+1}/{total}`"
        sent = bot.send_message(chat_id, text, reply_markup=kb, parse_mode='Markdown')
    last_messages[chat_id] = sent.message_id

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    data = call.data
    
    if data == "load_menu":
        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("📊 Excel", callback_data="load_excel"))
        kb.row(InlineKeyboardButton("📝 Text", callback_data="load_text"))
        kb.row(InlineKeyboardButton("🗑️ Clear ALL", callback_data="clear_all"))
        kb.row(InlineKeyboardButton("↩️ Back", callback_data="back_main"))
        bot.edit_message_text("📥 **Load Numbers:**", chat_id, call.message.message_id, reply_markup=kb, parse_mode='Markdown')
    
    elif data == "load_excel":
        bot.answer_callback_query(call.id, "📎 Send Excel file (.xlsx)")
        user_state[user_id] = {'waiting_excel': True}
    
    elif data == "load_text":
        bot.answer_callback_query(call.id, "📝 Send numbers as text")
        user_state[user_id] = {'waiting_text': True}
    
    elif data == "clear_all":
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "🗑️ Cleared!")
        send_current_number(chat_id, user_id)
    
    elif data == "back_main":
        bot.edit_message_text(WELCOME_TEXT, chat_id, call.message.message_id, reply_markup=main_menu_keyboard(), parse_mode='Markdown')
    
    elif data == "stats":
        cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=? AND status='pending'", (user_id,))
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,))
        total = cursor.fetchone()[0]
        bot.answer_callback_query(call.id, f"📊 Pending: {pending}/{total}")
    
    elif data.startswith("call_"):
        num_id = int(data.split("_")[1])
        cursor.execute("UPDATE numbers SET status='called' WHERE id=?", (num_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "📞 CALLING")
        user_state[user_id]['index'] += 1
        send_current_number(chat_id, user_id)
    
    elif data == "skip":
        user_state[user_id]['index'] += 1
        bot.answer_callback_query(call.id, "⏭️ Skipped!")
        send_current_number(chat_id, user_id)
    
    elif data == "back":
        user_state[user_id]['index'] = max(0, user_state[user_id]['index'] - 1)
        bot.answer_callback_query(call.id, "⬅️ Back")
        send_current_number(chat_id, user_id)

@bot.message_handler(content_types=['document'])
def handle_excel(message):
    user_id = message.from_user.id
    if user_id in user_state and user_state[user_id].get('waiting_excel'):
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(downloaded_file)
                tmp_path = tmp.name
            count = import_numbers(user_id, tmp_path, "excel")
            os.unlink(tmp_path)
            kb = InlineKeyboardMarkup()
            kb.row(InlineKeyboardButton("🚀 START", callback_data="start_calling"))
            bot.reply_to(message, f"✅ **Loaded {count} unique numbers!**\nStart calling 👇", reply_markup=kb, parse_mode='Markdown')
            del user_state[user_id]['waiting_excel']
        except Exception as e:
            bot.reply_to(message, f"❌ Excel error: {str(e)}")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    user_id = message.from_user.id
    if user_id in user_state and user_state[user_id].get('waiting_text'):
        count = import_numbers(user_id, message.text, "text")
        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("🚀 START", callback_data="start_calling"))
        bot.reply_to(message, f"✅ **Loaded {count} unique numbers!**\nStart calling 👇", reply_markup=kb, parse_mode='Markdown')
        del user_state[user_id]['waiting_text']
    else:
        send_current_number(message.chat.id, user_id)

def safe_polling():
    max_retries = 5
    retry_delay = 30
    while True:
        try:
            logger.info("🚀 SpeedCallerBot v4 — Polling START")
            requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset=-1", timeout=5)
            time.sleep(2)
            bot.polling(non_stop=True, interval=0.5, timeout=25, long_polling_timeout=25)
        except Exception as e:
            logger.error(f"🚨 Polling crashed: {str(e)[:100]}")
            if "409" in str(e):
                logger.warning("🔄 409 Conflict — HARD RESET")
                try:
                    requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset=-1")
                except: pass
                time.sleep(120)
            else:
                time.sleep(retry_delay)
            retry_delay = min(retry_delay * 1.5, 300)
            max_retries -= 1
            if max_retries <= 0:
                logger.error("💀 Max retries — restart in 10min")
                time.sleep(600)
                max_retries = 5

if __name__ == "__main__":
    logger.info("🚀 SpeedCallerBot v4 — FULLY ARMED")
    safe_polling()
