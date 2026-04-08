import os
import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
logger.info("Bot initialized")

# Глобальная база данных
conn = sqlite3.connect("numbers.db", check_same_thread=False)
cursor = conn.cursor()

# Создаём продвинутую таблицу
cursor.execute("""
CREATE TABLE IF NOT EXISTS numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    number TEXT UNIQUE,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    position INTEGER DEFAULT 0
)
""")
conn.commit()
logger.info("Database ready")

# Состояние пользователей
user_states = {}  # {user_id: {'position': 0, 'total': 0, 'current_rowid': None}}
user_message_ids = {}  # {user_id: message_id} для редактирования

print("🚀 SpeedCallerBot v2 - BASE READY")

# ===== ЧАСТЬ 2.1: СТАРТ + АВТОУДАЛЕНИЕ =====

def delete_previous_message(user_id, current_message_id=None):
    """Удаляет предыдущее сообщение бота"""
    if user_id in user_message_ids:
        try:
            bot.delete_message(user_id, user_message_ids[user_id])
            logger.info(f"Deleted message {user_message_ids[user_id]} for user {user_id}")
        except:
            pass  # Игнорируем ошибки удаления
    if current_message_id:
        user_message_ids[user_id] = current_message_id

@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📊 Demo Numbers", callback_data="demo"))
    markup.row(InlineKeyboardButton("📈 Stats", callback_data="stats"))
    markup.row(InlineKeyboardButton("🗑️ Clear", callback_data="clear"))
    
    # Удаляем старое сообщение и отправляем новое
    delete_previous_message(user_id)
    
    sent_msg = bot.send_message(
        chat_id, 
        "🚀 SpeedCallerBot v2 READY!\n\n"
        "📱 Demo → CALL → Skip/Back\n"
        "✅ Auto-delete messages",
        reply_markup=markup
    )
    user_message_ids[user_id] = sent_msg.message_id
    user_states[user_id] = {'position': 0}
    logger.info(f"Start for user {user_id}")

print("🚀 SpeedCallerBot v2 - PART 2.1 READY (Auto-delete ON)")

# ===== ЧАСТЬ 3: CALL/SKIP/BACK с автообновлением =====

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    logger.info(f"Callback {call.data} from user {user_id}")
    
    # АВТОУДАЛЕНИЕ старого сообщения
    if user_id in user_message_ids and user_message_ids[user_id] != message_id:
        try:
            bot.delete_message(chat_id, user_message_ids[user_id])
        except:
            pass
    
    if call.data == "demo":
        # Загрузка демо номеров
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        for i in range(150):
            cursor.execute("INSERT INTO numbers (user_id, number, status) VALUES (?, ?, 'pending')",
                          (user_id, f"+1-555-{i:03d}-{i:04d}"))
        conn.commit()
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("☎️ CALL", callback_data="call"))
        markup.row(InlineKeyboardButton("📊 STATS", callback_data="stats"))
        
        text = "✅ 150 DEMO numbers loaded!\n👇 Click CALL to start"
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        
    elif call.data == "stats":
        stats = cursor.execute(
            "SELECT status, COUNT(*) FROM numbers WHERE user_id=? GROUP BY status", 
            (user_id,)
        ).fetchall()
        total = sum([c for _, c in stats])
        
        text = f"📈 STATS (Total: {total})\n"
        for status, count in stats:
            text += f"• {status.upper()}: {count}\n"
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("☎️ CALL", callback_data="call"))
        markup.row(InlineKeyboardButton("📊 REFRESH", callback_data="stats"))
        
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "call":
        # Показываем номер для звонка
        numbers = cursor.execute(
            "SELECT id, number FROM numbers WHERE user_id=? AND status='pending' ORDER BY id LIMIT 100", 
            (user_id,)
        ).fetchall()
        
        if not numbers:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("📊 Demo Numbers", callback_data="demo"))
            bot.edit_message_text("📭 No numbers! Load DEMO first.", chat_id, message_id, reply_markup=markup)
            return
        
        # Текущая позиция
        position = user_states.get(user_id, {}).get('position', 0)
        current = numbers[position % len(numbers)]
        current_id, current_number = current
        
        user_states[user_id] = {'position': position, 'current_id': current_id}
        
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("☎️ CALL", callback_data="call"),
            InlineKeyboardButton("⏭️ SKIP", callback_data="skip")
        )
        markup.row(
            InlineKeyboardButton("⬅️ BACK", callback_data="back"),
            InlineKeyboardButton("📊 STATS", callback_data="stats")
        )
        
        text = (
            f"📞 #{position+1} of {len(numbers)}\n\n"
            f"<code>{current_number}</code>"
        )
        
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='HTML')
        user_message_ids[user_id] = message_id
    
    elif call.data == "skip":
        state = user_states.get(user_id, {})
        if state.get('current_id'):
            cursor.execute(
                "UPDATE numbers SET status='skipped' WHERE id=?", 
                (state['current_id'],)
            )
            conn.commit()
        
        # Следующий номер
        new_position = (state.get('position', 0) + 1) % 100
        user_states[user_id] = {'position': new_position}
        
        bot.answer_callback_query(call.id, "⏭️ SKIPPED → Next!")
    
    elif call.data == "back":
        state = user_states.get(user_id, {})
        new_position = max(0, state.get('position', 0) - 1)
        user_states[user_id] = {'position': new_position}
        bot.answer_callback_query(call.id, "⬅️ Back to previous")
    
    elif call.data == "clear":
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        conn.commit()
        user_states[user_id] = {'position': 0}
        bot.edit_message_text("🗑️ Database CLEARED!", chat_id, message_id)

print("🚀 SpeedCallerBot v2 - PART 3 READY (CALL/SKIP/BACK)")

# ===== ЧАСТЬ 3: CALL/SKIP/BACK с автообновлением =====

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    logger.info(f"Callback {call.data} from user {user_id}")
    
    # АВТОУДАЛЕНИЕ старого сообщения
    if user_id in user_message_ids and user_message_ids[user_id] != message_id:
        try:
            bot.delete_message(chat_id, user_message_ids[user_id])
        except:
            pass
    
    if call.data == "demo":
        # Загрузка демо номеров
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        for i in range(150):
            cursor.execute("INSERT INTO numbers (user_id, number, status) VALUES (?, ?, 'pending')",
                          (user_id, f"+1-555-{i:03d}-{i:04d}"))
        conn.commit()
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("☎️ CALL", callback_data="call"))
        markup.row(InlineKeyboardButton("📊 STATS", callback_data="stats"))
        
        text = "✅ 150 DEMO numbers loaded!\n👇 Click CALL to start"
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        
    elif call.data == "stats":
        stats = cursor.execute(
            "SELECT status, COUNT(*) FROM numbers WHERE user_id=? GROUP BY status", 
            (user_id,)
        ).fetchall()
        total = sum([c for _, c in stats])
        
        text = f"📈 STATS (Total: {total})\n"
        for status, count in stats:
            text += f"• {status.upper()}: {count}\n"
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("☎️ CALL", callback_data="call"))
        markup.row(InlineKeyboardButton("📊 REFRESH", callback_data="stats"))
        
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    
    elif call.data == "call":
        # Показываем номер для звонка
        numbers = cursor.execute(
            "SELECT id, number FROM numbers WHERE user_id=? AND status='pending' ORDER BY id LIMIT 100", 
            (user_id,)
        ).fetchall()
        
        if not numbers:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("📊 Demo Numbers", callback_data="demo"))
            bot.edit_message_text("📭 No numbers! Load DEMO first.", chat_id, message_id, reply_markup=markup)
            return
        
        # Текущая позиция
        position = user_states.get(user_id, {}).get('position', 0)
        current = numbers[position % len(numbers)]
        current_id, current_number = current
        
        user_states[user_id] = {'position': position, 'current_id': current_id}
        
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("☎️ CALL", callback_data="call"),
            InlineKeyboardButton("⏭️ SKIP", callback_data="skip")
        )
        markup.row(
            InlineKeyboardButton("⬅️ BACK", callback_data="back"),
            InlineKeyboardButton("📊 STATS", callback_data="stats")
        )
        
        text = (
            f"📞 #{position+1} of {len(numbers)}\n\n"
            f"<code>{current_number}</code>"
        )
        
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='HTML')
        user_message_ids[user_id] = message_id
    
    elif call.data == "skip":
        state = user_states.get(user_id, {})
        if state.get('current_id'):
            cursor.execute(
                "UPDATE numbers SET status='skipped' WHERE id=?", 
                (state['current_id'],)
            )
            conn.commit()
        
        # Следующий номер
        new_position = (state.get('position', 0) + 1) % 100
        user_states[user_id] = {'position': new_position}
        
        bot.answer_callback_query(call.id, "⏭️ SKIPPED → Next!")
    
    elif call.data == "back":
        state = user_states.get(user_id, {})
        new_position = max(0, state.get('position', 0) - 1)
        user_states[user_id] = {'position': new_position}
        bot.answer_callback_query(call.id, "⬅️ Back to previous")
    
    elif call.data == "clear":
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        conn.commit()
        user_states[user_id] = {'position': 0}
        bot.edit_message_text("🗑️ Database CLEARED!", chat_id, message_id)

print("🚀 SpeedCallerBot v2 - PART 3 READY (CALL/SKIP/BACK)")

# ===== ЧАСТЬ 4: EXCEL + ТЕКСТ ПАРСЕР =====

@bot.message_handler(content_types=["document", "text"])
def handle_input(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    try:
        if message.document:
            # EXCEL файл
            if "spreadsheet" in message.document.mime_type:
                bot.reply_to(message, "📥 Processing Excel... ⏳")
                file_info = bot.get_file(message.document.file_id)
                file_bytes = bot.download_file(file_info.file_path)
                added = import_excel_numbers(user_id, file_bytes)
            else:
                bot.reply_to(message, "❌ Send .XLSX or TEXT with numbers")
                return
        else:
            # ТЕКСТ сообщение
            bot.reply_to(message, "📥 Processing TEXT... ⏳")
            text = message.text.strip()
            added = import_text_numbers(user_id, text)
        
        # Результат импорта
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("☎️ CALL", callback_data="call"))
        markup.row(InlineKeyboardButton("📊 STATS", callback_data="stats"))
        
        bot.send_message(
            chat_id,
            f"✅ {added} NUMBERS imported!\n👇 Start CALLING",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Import error: {e}")
        bot.reply_to(message, "❌ Failed. Send TEXT or .XLSX")

def import_text_numbers(user_id, text):
    """Парсит номера из текста"""
    import re
    
    cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
    
    # Ищет все номера телефонов
    phone_pattern = r'[\+]?[\d\s\-\(\)\.]{8,20}'
    phones = re.findall(phone_pattern, text)
    
    added = 0
    for phone in phones:
        # Очищаем и форматируем
        clean = ''.join(filter(str.isdigit, phone))
        if len(clean) >= 8:
            if len(clean) > 15:
                clean = clean[-10:]  # Берём последние 10 цифр
            formatted = f"+1-{clean[-10:-7]}-{clean[-7:-4]}-{clean[-4:]}"
            
            cursor.execute(
                "INSERT OR IGNORE INTO numbers (user_id, number, status) VALUES (?, ?, 'pending')",
                (user_id, formatted)
            )
            added += 1
    
    conn.commit()
    return added

def import_excel_numbers(user_id, file_bytes):
    """Парсит номера из Excel"""
    import openpyxl
    import tempfile
    import time
    import os
    
    added = 0
    temp_file = f"temp_{int(time.time())}_{user_id}.xlsx"
    
    try:
        with open(temp_file, "wb") as f:
            f.write(file_bytes)
        
        wb = openpyxl.load_workbook(temp_file, data_only=True)
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if cell:
                        number = str(cell).strip()
                        clean = ''.join(filter(str.isdigit, number))
                        if len(clean) >= 8:
                            formatted = f"+1-{clean[-10:-7]}-{clean[-7:-4]}-{clean[-4:]}"
                            cursor.execute(
                                "INSERT OR IGNORE INTO numbers (user_id, number, status) VALUES (?, ?, 'pending')",
                                (user_id, formatted)
                            )
                            added += 1
        
        conn.commit()
        
    finally:
        try:
            os.remove(temp_file)
        except:
            pass
    
    return added

print("🚀 SpeedCallerBot v2 - PART 4 READY (TEXT + EXCEL)")

# ===== ЧАСТЬ 5: TELEGRAM CALL + RESET + FINISH =====

@bot.callback_query_handler(func=lambda call: call.data == "call_phone")
def call_phone(call):
    """Telegram звонок на номер"""
    user_id = call.from_user.id
    state = user_states.get(user_id, {})
    
    if state.get('current_number'):
        # Telegram call URL
        call_url = f"tg://call?phone={state['current_number'].replace('+', '').replace('-', '').replace(' ', '')}"
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("☎️ CALL AGAIN", callback_data="call"))
        markup.row(InlineKeyboardButton("⏭️ NEXT", callback_data="skip"))
        
        text = f"📞 CALLING...\n{state['current_number']}\n\n✅ Marked as CALLED"
        cursor.execute("UPDATE numbers SET status='called' WHERE id=?", (state['current_id'],))
        conn.commit()
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=["reset"])
def reset_db(message):
    """Сброс базы для пользователя"""
    user_id = message.from_user.id
    cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
    conn.commit()
    user_states[user_id] = {'position': 0}
    bot.reply_to(message, "🔄 Database RESET! Send new numbers.")

# Добавляем кнопку CALL в CALL handler (строка в ЧАСТИ 3)
# В markup CALL замени:
# InlineKeyboardButton("☎️ CALL", callback_data="call_phone")  # вместо "call"

# ФИНАЛЬНЫЙ POLLING с обработкой ошибок
if __name__ == "__main__":
    logger.info("🚀 SpeedCallerBot v2 FULL STARTING...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(15)
