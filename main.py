# SpeedCallerBot v5 — WEBHOOK версия (НИКОГДА 409!)
import os
import re
import sqlite3
import logging
import time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request, abort
import openpyxl
import tempfile
import requests
import threading

# Логи
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

# Инициализация Flask
app = Flask(__name__)

# База данных с UNIQUE номерами
conn = sqlite3.connect("speedcaller_v5.db", check_same_thread=False)
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

# Состояние пользователей и сообщения
user_state = {}
last_messages = {}

WELCOME_TEXT = """
👋 **SpeedCallerBot v5 — WEBHOOK**

📞 **Fast client database calling**

**Максимум звонков в день:**
• Загрузи Excel или текст с номерами
• Нажми CALL → открывается звонок
• SKIP → следующий номер мгновенно
• BACK → предыдущий номер

**НЕТ ЛИМИТОВ на номера!**
Готов? Нажми ➕ 👇
"""

def delete_last_message(chat_id):
    """Удаляет последнее сообщение"""
    if chat_id in last_messages:
        try:
            bot.delete_message(chat_id, last_messages[chat_id])
        except:
            pass

def main_menu_keyboard():
    """Главное меню"""
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("➕ Load Numbers", callback_data="load_menu"))
    return kb

# ===== Импорт и нормализация номеров =====

def normalize_phone(phone):
    """Нормализация номеров любой страны"""
    # Убираем всё кроме цифр и +
    clean = re.sub(r'[^\d+]', '', str(phone))
    
    if len(clean) < 8:
        return None
    
    # Россия: 8xxx → +7xxx
    if clean.startswith('8') and len(clean) == 11:
        clean = '7' + clean[1:]
    
    # Добавляем + если нет кода страны
    if not clean.startswith('+'):
        clean = '+' + clean
    
    # E.164 стандарт (макс 15 символов)
    return clean[-15:]

def import_numbers(user_id, data, source="manual"):
    """Импорт с автоудалением дублей"""
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
        except Exception as e:
            logger.error(f"Excel error: {e}")
            return 0
    else:  # text
        numbers = [line.strip() for line in data.split('\n') if line.strip()]
    
    # Импорт с проверкой дублей
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
            except Exception as e:
                logger.error(f"DB error: {e}")
                continue
    
    conn.commit()
    logger.info(f"User {user_id}: added {count_added} unique numbers")
    return count_added

# ===== Команды старт =====
@bot.message_handler(commands=['start'])
def start_handler(message):
    """Старт бота"""
    delete_last_message(message.chat.id)
    sent = bot.send_message(
        message.chat.id, 
        WELCOME_TEXT, 
        reply_markup=main_menu_keyboard(), 
        parse_mode='Markdown'
    )
    last_messages[message.chat.id] = sent.message_id

# ===== Навигация между номерами =====

def get_user_numbers(user_id):
    """Получить pending номера пользователя"""
    cursor.execute("""
        SELECT id, phone FROM numbers 
        WHERE user_id=? AND status='pending' 
        ORDER BY created_at ASC
    """, (user_id,))
    return cursor.fetchall()

def get_current_number(user_id):
    """Текущий номер + индекс"""
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
    """Показать текущий номер с кнопками"""
    delete_last_message(chat_id)
    
    number_data, index, total = get_current_number(user_id)
    
    if not number_data:
        sent = bot.send_message(
            chat_id, 
            "📭 **Номера закончились!**\n\nНажми ➕ чтобы загрузить новые", 
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
        
        # Unicode + для красивого отображения
        phone_display = phone.replace('+', '＋')
        text = f"**📱 {phone_display}**\n\n**Прогресс:** `{index+1}/{total}`"
        
        sent = bot.send_message(chat_id, text, reply_markup=kb, parse_mode='Markdown')
    
    last_messages[chat_id] = sent.message_id

# ===== Обработчики кнопок =====
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    data = call.data
    
    # Главное меню загрузки
    if data == "load_menu":
        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("📊 Excel", callback_data="load_excel"))
        kb.row(InlineKeyboardButton("📝 Text", callback_data="load_text"))
        kb.row(InlineKeyboardButton("🗑️ Clear ALL", callback_data="clear_all"))
        kb.row(InlineKeyboardButton("↩️ Back", callback_data="back_main"))
        
        bot.edit_message_text(
            "📥 **Загрузить номера:**", 
            chat_id, 
            call.message.message_id, 
            reply_markup=kb, 
            parse_mode='Markdown'
        )
    
    # Excel загрузка
    elif data == "load_excel":
        bot.answer_callback_query(call.id, "📎 Отправь Excel файл (.xlsx)")
        user_state[user_id] = {'waiting_excel': True}
    
    # Text загрузка
    elif data == "load_text":
        bot.answer_callback_query(call.id, "📝 Отправь номера текстом (по строкам)")
        user_state[user_id] = {'waiting_text': True}
    
    # Очистить все
    elif data == "clear_all":
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "🗑️ Все номера удалены!")
        send_current_number(chat_id, user_id)
    
    # Назад в главное меню
    elif data == "back_main":
        bot.edit_message_text(
            WELCOME_TEXT, 
            chat_id, 
            call.message.message_id, 
            reply_markup=main_menu_keyboard(), 
            parse_mode='Markdown'
        )
    
    # Статистика
    elif data == "stats":
        cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=? AND status='pending'", (user_id,))
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,))
        total = cursor.fetchone()[0]
        bot.answer_callback_query(call.id, f"📊 Осталось: {pending}/{total}")
    
    # CALL номер
    elif data.startswith("call_"):
        num_id = int(data.split("_")[1])
        cursor.execute("UPDATE numbers SET status='called' WHERE id=?", (num_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "📞 Звони!")
        user_state[user_id]['index'] += 1
        send_current_number(chat_id, user_id)
    
    # SKIP номер
    elif data == "skip":
        user_state[user_id]['index'] += 1
        bot.answer_callback_query(call.id, "⏭️ Пропущено!")
        send_current_number(chat_id, user_id)
    
    # BACK
    elif data == "back":
        user_state[user_id]['index'] = max(0, user_state[user_id]['index'] - 1)
        bot.answer_callback_query(call.id, "⬅️ Назад")
        send_current_number(chat_id, user_id)

# ===== Flask Webhook =====
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Получение обновлений от Telegram"""
    if request.headers.get('content-type') == 'application/json':
        json_data = request.get_json()
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
        return ''
    else:
        abort(403)

# ===== Обработка файлов и текста =====
@bot.message_handler(content_types=['document'])
def handle_excel(message):
    """Обработка Excel файлов"""
    user_id = message.from_user.id
    if user_id in user_state and user_state[user_id].get('waiting_excel'):
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Сохраняем временно
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(downloaded_file)
                tmp_path = tmp.name
            
            # Импорт
            count = import_numbers(user_id, tmp_path, "excel")
            os.unlink(tmp_path)  # Удаляем временный файл
            
            # Кнопка старта
            kb = InlineKeyboardMarkup()
            kb.row(InlineKeyboardButton("🚀 НАЧАТЬ", callback_data="start_calling"))
            
            bot.reply_to(message, 
                f"✅ **Загружено {count} уникальных номеров!**\n\nНажми НАЧАТЬ 👇", 
                reply_markup=kb, parse_mode='Markdown')
            
            # Сбрасываем состояние
            del user_state[user_id]['waiting_excel']
            
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка Excel: {str(e)}")

@bot.message_handler(func=lambda m: True)
def handle_text_or_default(message):
    """Текст номеров или дефолт"""
    user_id = message.from_user.id
    
    # Если ждём текст номеров
    if user_id in user_state and user_state[user_id].get('waiting_text'):
        count = import_numbers(user_id, message.text, "text")
        
        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("🚀 НАЧАТЬ", callback_data="start_calling"))
        
        bot.reply_to(message, 
            f"✅ **Загружено {count} уникальных номеров!**\n\nНажми НАЧАТЬ 👇", 
            reply_markup=kb, parse_mode='Markdown')
        
        del user_state[user_id]['waiting_text']
    
    # Любое другое сообщение = показываем текущий номер
    else:
        send_current_number(message.chat.id, user_id)

# Дополнительный callback для старта
@bot.callback_query_handler(func=lambda call: call.data == "start_calling")
def start_calling(call):
    """Запуск просмотра номеров"""
    send_current_number(call.message.chat.id, call.from_user.id)

# ===== Запуск WEBHOOK =====
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    if request.headers.get('content-type') == 'application/json':
        json_data = request.get_json()
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
        return '', 200
    else:
        abort(403)

@app.route('/')
def index():
    """Health check"""
    return "SpeedCallerBot v5 OK"

def run_flask():
    """Запуск Flask сервера"""
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    logger.info("🚀 SpeedCallerBot v5 — WEBHOOK ARMED")
    
    # УСТАНОВИ WEBHOOK!
    bot.remove_webhook()
    time.sleep(2)
    bot.set_webhook(url=f"https://speedcaller-bot-v2.onrender.com/{TOKEN}")  # ← ТВОЙ URL!
    
    # Запуск Flask
    run_flask()
