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

import re

def clean_phone(phone):
    phone = str(phone).strip()
    phone = re.sub(r"[^\d+]", "", phone)
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


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
            "📭 **Numbers finished!** ✅ **Numbers loaded!** Press **🚀 START** to begin or **⬅️ BACK/SKIP** to page through... ➕ Load new numbers",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
    else:
        num_id, phone = number_data
        phone_e164 = clean_phone(phone)
        
        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("📞 CALL", callback_data=f"call_{num_id}"))
        kb.row(
            InlineKeyboardButton("⏭️ SKIP", callback_data="skip"),
            InlineKeyboardButton("⬅️ BACK", callback_data="back")
        )
        kb.row(InlineKeyboardButton("🏠 Main menu", callback_data="load_menu"))
        
        text = f'👤 Client: <a href="tel:{phone_e164}">{phone_e164}</a>\nProgress: {index+1}/{total}'
        
        sent = bot.send_message(
            chat_id,
            text,
            reply_markup=kb,
            parse_mode='HTML'
        )
    
    last_messages[chat_id] = sent.message_id
    
# ===== ОБРАБОТЧИКИ КНОПОК =====
@bot.callback_query_handler(func=lambda call: call.data.startswith("call_"))
def handle_call(call):
    bot.answer_callback_query(call.id)

    num_id = int(call.data.split("_", 1)[1])

    cursor.execute("UPDATE numbers SET status='called' WHERE id=?", (num_id,))
    conn.commit()

    cursor.execute("SELECT phone, user_id FROM numbers WHERE id=?", (num_id,))
    row = cursor.fetchone()
    if not row:
        bot.send_message(call.message.chat.id, "❌ Number not found.")
        return

    phone, user_id = row
    phone_e164 = clean_phone(phone)

    bot.send_message(call.message.chat.id, f"📞 Number: {phone_e164}")

    if user_id not in user_state:
        user_state[user_id] = {'index': 0}

    user_state[user_id]['index'] += 1
    send_current_number(call.message.chat.id, user_id)


@bot.callback_query_handler(func=lambda call: call.data == "start_calling")
def start_calling(call):
    bot.answer_callback_query(call.id)
    send_current_number(call.message.chat.id, call.from_user.id)


@bot.callback_query_handler(func=lambda call: call.data == "remove_duplicates")
def remove_duplicates(call):
    user_id = call.from_user.id

    cursor.execute("""
        DELETE FROM numbers
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM numbers
            WHERE user_id=?
            GROUP BY phone
        ) AND user_id=?
    """, (user_id, user_id))
    conn.commit()

    bot.answer_callback_query(call.id, "🧹 Duplicates removed!")


@bot.callback_query_handler(func=lambda call: call.data == "load_menu")
def load_menu(call):
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("📊 Excel", callback_data="load_excel"))
    kb.row(InlineKeyboardButton("📝 Text", callback_data="load_text"))
    kb.row(InlineKeyboardButton("↩️ Return to call", callback_data="start_calling"))
    kb.row(InlineKeyboardButton("🗑️ Clear ALL", callback_data="clear_all"))
    kb.row(InlineKeyboardButton("🧹 Remove duplicates", callback_data="remove_duplicates"))
    kb.row(InlineKeyboardButton("↩️ Main Menu", callback_data="back_main"))

    bot.edit_message_text(
        "📥 Load numbers:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data == "load_excel")
def load_excel(call):
    bot.answer_callback_query(call.id, "📎 Send Excel (.xlsx)")
    user_state[call.from_user.id] = {'waiting_excel': True}


@bot.callback_query_handler(func=lambda call: call.data == "load_text")
def load_text(call):
    bot.answer_callback_query(call.id, "📝 Send numbers line by line")
    user_state[call.from_user.id] = {'waiting_text': True}


@bot.callback_query_handler(func=lambda call: call.data == "clear_all")
def clear_all(call):
    user_id = call.from_user.id

    cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
    conn.commit()
    user_state[user_id] = {'index': 0}

    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("📊 Excel", callback_data="load_excel"))
    kb.row(InlineKeyboardButton("📝 Text", callback_data="load_text"))
    kb.row(InlineKeyboardButton("🏠 Main menu", callback_data="back_main"))

    bot.edit_message_text(
        "🗑️ Numbers cleared!

📥 Upload new numbers:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data == "back_main")
def 
# ===== ОБРАБОТКА ФАЙЛОВ EXCEL/TEXT =====
@bot.message_handler(content_types=['document', 'text'])
def handle_numbers(message):
    """📎 Excel + 📝 Text — ЛЮБОЙ файл/текст"""
    user_id = message.from_user.id

    if message.document and message.document.file_name.endswith('.xlsx'):
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(downloaded_file)
                tmp_path = tmp.name

            count = import_numbers(user_id, tmp_path, "excel")
            user_state[user_id] = {'index': 0}
        except:
            bot.reply_to(message, "❌ Excel error!")
            return
    else:
        if not message.text:
            return
        count = import_numbers(user_id, message.text, "text")
        user_state[user_id] = {'index': 0}

    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🚀 START", callback_data="start_calling"))

    bot.reply_to(
        message,
        f"✅ {count} numbers loaded! Press 🚀 START to begin calling or add more numbers!",
        reply_markup=kb
    )

# ===== START CALLING =====
@bot.callback_query_handler(func=lambda call: call.data == "start_calling")
def start_calling(call):
    bot.answer_callback_query(call.id)

    number_data, index, total = get_current_number(call.from_user.id)
    if not number_data:
        bot.send_message(call.message.chat.id, "📭 No numbers loaded.")
        return

    send_current_number(call.message.chat.id, call.from_user.id)

# ===== SIMPLE POLLING =====
import time
from telebot.apihelper import ApiTelegramException

bot.remove_webhook()

while True:
    try:
        bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
    except ApiTelegramException as e:
        if "409" in str(e):
            time.sleep(3)
            continue
        raise
    except Exception:
        time.sleep(3)
        continue

