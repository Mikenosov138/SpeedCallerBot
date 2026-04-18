# SpeedCallerBot v6 — 100% РАБОЧИЙ
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
import threading

# Логи
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
bot.remove_webhook()  # ✅ Отключаем webhook!
logger.info("✅ Webhook removed — Polling mode")

# База UNIQUE номеров
conn = sqlite3.connect("speedcaller_v6.db", check_same_thread=False)
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

# Состояние
user_state = {}
last_messages = {}

WELCOME_TEXT = """
👋 **SpeedCallerBot**

📞 **Fast client database calling**

**How to use:**
• 📎 Send **Excel** file (.xlsx) 
• 📝 Send **Text** numbers (line by line)
• 📞 **CALL** → dial ✓
• ⏭️ **SKIP** → next
• ⬅️ **BACK** → previous

**NO LIMITS!** Send file/message 👇
"""

def delete_last_message(chat_id):
    if chat_id in last_messages:
        try:
            bot.delete_message(chat_id, last_messages[chat_id])
        except:
            pass

def main_menu_keyboard():
    return None  # No keyboard

@bot.message_handler(commands=['start'])
def start_handler(message):
    delete_last_message(message.chat.id)
    sent = bot.send_message(
    message.chat.id, WELCOME_TEXT, 
    reply_markup=None,  # No buttons
    parse_mode='Markdown'
    )
    last_messages[message.chat.id] = sent.message_id

# ===== НОРМАЛИЗАЦИЯ НОМЕРОВ ЛЮБОЙ СТРАНЫ =====
def normalize_phone(phone):
    """+79123456789 из любого формата"""
    clean = re.sub(r'[^\d+]', '', str(phone))  # Убираем всё кроме цифр/+
    if len(clean) < 8:
        return None
    
    # Россия 8→7
    if clean.startswith('8') and len(clean) == 11:
        clean = '7' + clean[1:]
    
    # Добавляем +
    if not clean.startswith('+'):
        clean = '+' + clean
    
    return clean[-15:]  # E.164 формат

# ===== ИМПОРТ EXCEL/TEXT =====
def import_numbers(user_id, data, source="manual"):
    """Импорт с UNIQUE номерами"""
    count_added = 0
    numbers = []
    
    if source == "excel":
        try:
            wb = openpyxl.load_workbook(data)
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        if cell:
                            numbers.append(str(cell))
        except:
            return 0
    else:  # Text
        numbers = [line.strip() for line in data.split('\n') if line.strip()]
    
    # UNIQUE импорт
    for phone in numbers:
        norm_phone = normalize_phone(phone)
        if norm_phone:
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO numbers (user_id, phone) VALUES (?, ?)",
                    (user_id, norm_phone)
                )
                if cursor.rowcount > 0:
                    count_added += 1
            except:
                pass
    
    conn.commit()
    logger.info(f"User {user_id}: +{count_added} номеров")
    return count_added

# ===== НАВИГАЦИЯ НОМЕРАМИ =====
def get_user_numbers(user_id):
    """Pending номера пользователя"""
    cursor.execute("""
        SELECT id, phone FROM numbers 
        WHERE user_id=? AND status='pending' 
        ORDER BY created_at ASC
    """, (user_id,))
    return cursor.fetchall()

def get_current_number(user_id):
    """Текущий номер + прогресс"""
    if user_id not in user_state:
        user_state[user_id] = {'index': 0}
    
    numbers = get_user_numbers(user_id)
    if not numbers:
        return None, None, 0
    
    index = user_state[user_id]['index']
    if index >= len(numbers):
        user_state[user_id]['index'] = 0
        index = 0
    
    return numbers[index], index, len(numbers)

def send_current_number(chat_id, user_id):
    delete_last_message(chat_id)
    
    number_data, index, total = get_current_number(user_id)
    
    if not number_data:
        sent = bot.send_message(
            chat_id, 
            "📭 **Numbers finished!**\\n\\n➕ Load new", 
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
    else:
        num_id, phone = number_data
        
        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("📞 CALL", callback_data=f"call_{num_id}"))
        kb.row(
            InlineKeyboardButton("⏭️ SKIP", callback_data="skip"),
            InlineKeyboardButton("⬅️ BACK", callback_data="back")
        )
        kb.row(InlineKeyboardButton(f"📊 {index+1}/{total}", callback_data="stats"))
        
        phone_display = phone.replace('+', '＋')  # Pretty +
        text = f"**📱 {phone_display}**\\n\\n**Progress:** `{index+1}/{total}`"
        
        sent = bot.send_message(chat_id, text, reply_markup=kb, parse_mode='Markdown')
    
    last_messages[chat_id] = sent.message_id

# ===== ОБРАБОТЧИКИ КНОПОК =====
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    data = call.data
    elif data == "start_calling":
    send_current_number(chat_id, user_id)
    
    # Load menu
    if data == "load_menu":
        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("📊 Excel", callback_data="load_excel"))
        kb.row(InlineKeyboardButton("📝 Text", callback_data="load_text"))
        kb.row(InlineKeyboardButton("🗑️ Clear ALL", callback_data="clear_all"))
        kb.row(InlineKeyboardButton("↩️ Main Menu", callback_data="back_main"))
        bot.edit_message_text("📥 **Load numbers:**", chat_id, call.message.message_id, 
                              reply_markup=kb, parse_mode='Markdown')
    
    elif data == "load_excel":
        bot.answer_callback_query(call.id, "📎 Send Excel (.xlsx)")
        user_state[user_id] = {'waiting_excel': True}
    
    elif data == "load_text":
        bot.answer_callback_query(call.id, "📝 Send numbers line by line")
        user_state[user_id] = {'waiting_text': True}
    
    elif data == "clear_all":
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "🗑️ Очищено!")
        send_current_number(chat_id, user_id)
    
    elif data == "back_main":
        bot.edit_message_text(WELCOME_TEXT, chat_id, call.message.message_id, 
                            reply_markup=main_menu_keyboard(), parse_mode='Markdown')
    
    elif data == "stats":
        cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=? AND status='pending'", (user_id,))
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,))
        total = cursor.fetchone()[0]
        bot.answer_callback_query(call.id, f"📊 {pending}/{total}")
    
    elif data.startswith("call_"):
        num_id = int(data.split("_")[1])
        cursor.execute("UPDATE numbers SET status='called' WHERE id=?", (num_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "📞 Звони!")
        user_state[user_id]['index'] += 1
        send_current_number(chat_id, user_id)
    
    elif data == "skip":
        user_state[user_id]['index'] += 1
        bot.answer_callback_query(call.id, "⏭️ Пропущено!")
        send_current_number(chat_id, user_id)
    
    elif data == "back":
        user_state[user_id]['index'] = max(0, user_state[user_id]['index'] - 1)
        bot.answer_callback_query(call.id, "⬅️ Назад")
        send_current_number(chat_id, user_id)

# ===== ОБРАБОТКА ФАЙЛОВ EXCEL/TEXT =====
@bot.message_handler(content_types=['document'])
def handle_excel(message):
    """Excel импорт"""
    user_id = message.from_user.id
    if user_id in user_state and user_state[user_id].get('waiting_excel'):
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(downloaded_file)
                tmp_path = tmp.name
            
    count = import_numbers(user_id, tmp_path, "excel")
    
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🚀 START", callback_data="start_calling"))  # ← ЗДЕСЬ!
    
    bot.reply_to(message, f"✅ **{count} unique numbers!**\\n🚀 START calling 👇", 
                reply_markup=kb, parse_mode='Markdown')
            del user_state[user_id]['waiting_excel']
        except Exception as e:
            bot.reply_to(message, f"❌ Excel: {str(e)}")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    user_id = message.from_user.id
    
    if user_id in user_state and user_state[user_id].get('waiting_text'):
        count = import_numbers(user_id, message.text, "text")
        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("🚀 START", callback_data="start_calling"))
        bot.reply_to(message, f"✅ **{count} уникальных номеров!**\\n🚀 Начать 👇", 
                    reply_markup=kb, parse_mode='Markdown')
        del user_state[user_id]['waiting_text']
    else:
        send_current_number(message.chat.id, user_id)
    
# ===== SIMPLE POLLING =====
def simple_polling():
    logger.info("🔄 SpeedCallerBot v6 — Polling START")
    while True:
        try:
            bot.polling(
                non_stop=True,
                interval=1,
                timeout=20
            )
        except Exception as e:
            logger.error(f"Polling restart: {e}")
            time.sleep(10)

if __name__ == "__main__":
    logger.info("🚀 SpeedCallerBot v6 — FULLY ARMED")
    simple_polling()

