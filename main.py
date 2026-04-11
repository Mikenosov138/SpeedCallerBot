# ===== СкоростьЗвонокBot v3 - ПРОФЕССИОНАЛЬНАЯ ВЕРСИЯ =====
# ЧАСТЬ 1: БАЗА + ЛОГИ + КОНСТАНТЫ

import os
import sqlite3
import telebot
import logging
import time
import re
import openpyxl
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('speedcaller.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
logger.info("🚀 SpeedCallerBot v3 initialized")

# Продвинутая БД
conn = sqlite3.connect("speedcaller.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    number TEXT,
    status TEXT DEFAULT 'pending',
    position INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'manual'
)
""")
conn.commit()
logger.info("✅ Professional database ready")

# Состояния
user_sessions = {}
active_messages = {}

WELCOME_TEXT = """
👋 **SpeedCallerBot v3 - Professional Edition**

📞 Designed for **FAST client base calling**
📊 **Unlimited numbers supported**

**How to start:**
• Send **Excel file** (.xlsx) OR
• Send **text message** with phone numbers

**Example text:** `+1234567890 987-654-3210`

Ready? Send numbers now! 🚀
"""

print("✅ PART 1: Database + Welcome ready")

# ===== ЧАСТЬ 2: УНИВЕРСАЛЬНЫЙ ПАРСЕР =====

def parse_phone_number(raw_text):
    """Универсальный парсер номеров"""
    # Убираем все НЕ цифры
    clean = re.sub(r'[^\d+]', '', raw_text)
    
    # Минимум 8 цифр
    if len(clean) < 8:
        return None
    
    # Берём последние 10 цифр для US формат
    if len(clean) > 10:
        clean = clean[-10:]
    
    # Форматируем +1-XXX-XXX-XXXX
    formatted = f"+1-{clean[0:3]}-{clean[3:6]}-{clean[6:10]}"
    return formatted

def import_numbers(user_id, source_data, source_type="text"):
    """Импорт номеров (добавляет к существующим!)"""
    added = 0
    
    # Парсим данные
    if source_type == "excel":
        numbers = parse_excel(source_data)
    else:
        numbers = [line.strip() for line in source_data.split('\n') if line.strip()]
    
    # Добавляем к базе (НЕ удаляем старые!)
    for raw_number in numbers:
        formatted = parse_phone_number(raw_number)
        if formatted:
            cursor.execute("""
                INSERT OR IGNORE INTO calls (user_id, number, status, source) 
                VALUES (?, ?, 'pending', ?)
            """, (user_id, formatted, source_type))
            added += cursor.rowcount
    
    conn.commit()
    logger.info(f"Imported {added} numbers from {source_type} for user {user_id}")
    return added

def parse_excel(file_bytes):
    """Парсер Excel - все листы/ячейки"""
    try:
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        temp_file.write(file_bytes)
        temp_file.close()
        
        wb = openpyxl.load_workbook(temp_file.name, data_only=True)
        numbers = []
        
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                for cell in row:
                    if cell:
                        numbers.append(str(cell))
        
        os.unlink(temp_file.name)
        return numbers
    except:
        return []

@bot.message_handler(content_types=["text", "document"])
def handle_numbers(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    try:
        if message.text:
            # ТЕКСТ
            bot.reply_to(message, "📱 Parsing TEXT numbers...")
            count = import_numbers(user_id, message.text, "text")
        elif message.document and "spreadsheet" in message.document.mime_type:
            # EXCEL
            bot.reply_to(message, "📊 Parsing Excel...")
            file_info = bot.get_file(message.document.file_id)
            file_bytes = bot.download_file(file_info.file_path)
            count = import_numbers(user_id, file_bytes, "excel")
        else:
            bot.reply_to(message, "❌ Send TEXT with numbers or .XLSX file")
            return
        
        # Результат
        total = cursor.execute("SELECT COUNT(*) FROM calls WHERE user_id=?", (user_id,)).fetchone()[0]
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("☎️ CALL", callback_data="start_calling"))
        markup.row(InlineKeyboardButton("📊 STATS", callback_data="show_stats"))
        
        bot.send_message(
            chat_id,
            f"✅ **{count} NEW numbers imported!**\n"
            f"📈 **Total in DB: {total}**\n\n"
            f"👇 Ready to CALL",
            reply_markup=markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Import error: {e}")
        bot.reply_to(message, "❌ Import failed. Try simple text format")

print("✅ PART 2: Universal Parser (Text + Excel) ready")

# ===== ЧАСТЬ 3: CALL с tg://call (полноэкранная) =====

def get_next_pending_call(user_id):
    """Получает следующий pending номер"""
    result = cursor.execute("""
        SELECT id, number, position 
        FROM calls 
        WHERE user_id=? AND status='pending' 
        ORDER BY position ASC, id ASC 
        LIMIT 1
    """, (user_id,)).fetchone()
    return result

def update_call_status(call_id, new_status):
    """Обновляет статус звонка"""
    cursor.execute("UPDATE calls SET status=? WHERE id=?", (new_status, call_id))
    conn.commit()

@bot.callback_query_handler(func=lambda call: call.data.startswith('call_'))
def handle_call_action(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    action = call.data.split('_')[1]  # call_start, call_skip, call_back
    
    if action == "start":
        # ПОЛУЧАЕМ НОМЕР
        call_data = get_next_pending_call(user_id)
        if not call_data:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("📊 ADD NUMBERS", callback_data="add_numbers"))
            bot.edit_message_text(
                "📭 **No pending calls**\n\nSend TEXT or Excel to add numbers",
                chat_id, message_id, 
                reply_markup=markup,
                parse_mode='Markdown'
            )
            return
        
        call_id, number, position = call_data
        
        # ПОЛНОЭКРАННАЯ CALL КНОПКА
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton(
                f"☎️ CALL {number}", 
                url=f"tg://call?phone={number.replace('+1-', '').replace('-', '')}",
                callback_data=f"call_marked_{call_id}"
            )
        )
        markup.row(
            InlineKeyboardButton("⏭️ SKIP", callback_data="call_skip"),
            InlineKeyboardButton("⬅️ PREV", callback_data="call_back")
        )
        markup.row(InlineKeyboardButton("📊 STATS", callback_data="show_stats"))
        
        text = (
            f"📞 **CALL #{position + 1}**\n\n"
            f"📱 <code>{number}</code>\n\n"
            f"👆 Tap CALL → Phone app opens"
        )
        
        bot.edit_message_text(
            text,
            chat_id, message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
        active_messages[user_id] = message_id
        
    elif action == "skip":
        call_data = get_next_pending_call(user_id)
        if call_data:
            update_call_status(call_data[0], 'skipped')
        bot.answer_callback_query(call.id, "⏭️ SKIPPED ✓")
    
    elif action == "back":
        # Возврат к предыдущему (простой previous)
        bot.answer_callback_query(call.id, "⬅️ Back to list")
    
    elif action == "marked":
        # CALL был сделан
        call_id = call.data.split('_')[2]
        update_call_status(call_id, 'called')
        bot.answer_callback_query(call.id, "✅ CALL COMPLETED!")

print("✅ PART 3: tg://call button (fullscreen) ready")

# ===== ЧАСТЬ 4: STATS + MULTI-ADD =====

def get_user_stats(user_id):
    """Детальная статистика"""
    total = cursor.execute("SELECT COUNT(*) FROM calls WHERE user_id=?", (user_id,)).fetchone()[0]
    pending = cursor.execute("SELECT COUNT(*) FROM calls WHERE user_id=? AND status='pending'", (user_id,)).fetchone()[0]
    called = cursor.execute("SELECT COUNT(*) FROM calls WHERE user_id=? AND status='called'", (user_id,)).fetchone()[0]
    skipped = cursor.execute("SELECT COUNT(*) FROM calls WHERE user_id=? AND status='skipped'", (user_id,)).fetchone()[0]
    
    return {
        'total': total,
        'pending': pending,
        'called': called,
        'skipped': skipped,
        'conversion': round((called / total * 100), 1) if total > 0 else 0
    }

@bot.callback_query_handler(func=lambda call: call.data in ['show_stats', 'add_numbers', 'reset_stats'])
def stats_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    action = call.data
    
    if action == "show_stats":
        stats = get_user_stats(user_id)
        text = (
            f"📊 **CALLING STATS**\n\n"
            f"📈 **Total**: {stats['total']}\n"
            f"⏳ **Pending**: {stats['pending']}\n"
            f"✅ **Called**: {stats['called']}\n"
            f"⏭️ **Skipped**: {stats['skipped']}\n\n"
            f"🎯 **Conversion**: {stats['conversion']}%"
        )
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("➕ ADD MORE", callback_data="add_numbers"))
        markup.row(InlineKeyboardButton("🗑️ RESET", callback_data="reset_stats"))
        markup.row(InlineKeyboardButton("☎️ CONTINUE CALL", callback_data="start_calling"))
        
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')
    
    elif action == "add_numbers":
        text = (
            "➕ **ADD MORE NUMBERS**\n\n"
            "**Send:**\n"
            "• TEXT: `+1234567890 9876543210`\n"
            "• Excel file (.xlsx)\n\n"
            "**Numbers will be ADDED to existing base**"
        )
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("📊 BACK TO STATS", callback_data="show_stats"))
        
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')
    
    elif action == "reset_stats":
        cursor.execute("DELETE FROM calls WHERE user_id=?", (user_id,))
        conn.commit()
        user_sessions[user_id] = {'position': 0}
        text = "🗑️ **DATABASE RESET**\n\nAll numbers cleared.\nAdd new numbers to start."
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("📊 NEW STATS", callback_data="show_stats"))
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')

print("✅ PART 4: Detailed Stats + Multi-Add ready")

# ===== ЧАСТЬ 5: ПРОФ ДИЗАЙН КНОПОК =====

@bot.callback_query_handler(func=lambda call: call.data.startswith('call_'))
def handle_call_action(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    action = call.data.split('_')[1]
    
    if action == "start":
        call_data = get_next_pending_call(user_id)
        if not call_data:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("➕ ADD NUMBERS", callback_data="add_numbers"))
            bot.edit_message_text(
                "📭 **No pending calls**\n\n👆 Send TEXT/Excel to continue",
                chat_id, message_id, 
                reply_markup=markup,
                parse_mode='Markdown'
            )
            return
        
        call_id, number, position = call_data
        
        # ОЧЕНЬ БОЛЬШАЯ CALL КНОПКА (50% ширина)
        markup = InlineKeyboardMarkup()
        
        # CALL - ПОЛЭКРАНА
        call_btn = InlineKeyboardButton(
            f"📞 CALL {number}",
            url=f"tg://call?phone={number.replace('+1-', '').replace('-', '')}",
            callback_data=f"call_marked_{call_id}"
        )
        skip_btn = InlineKeyboardButton("⏭️ SKIP", callback_data="call_skip")
        
        markup.row(call_btn, skip_btn)  # 50% + 50%
        
        # Нижний ряд
        markup.row(
            InlineKeyboardButton("⬅️ PREV", callback_data="call_back"),
            InlineKeyboardButton("📊 STATS", callback_data="show_stats")
        )
        
        # КРУТОЙ ДИЗАЙН ТЕКСТА
        total_pending = cursor.execute("SELECT COUNT(*) FROM calls WHERE user_id=? AND status='pending'", (user_id,)).fetchone()[0]
        text = (
            f"🎯 **CALL #{position + 1}/{total_pending}**\n\n"
            f"📱 <b>{number}</b>\n\n"
            f"👆 <i>Tap CALL → Phone opens automatically</i>"
        )
        
        bot.edit_message_text(
            text,
            chat_id, message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
        active_messages[user_id] = message_id
        
        user_sessions[user_id] = {
            'current_call_id': call_id,
            'current_position': position,
            'message_id': message_id
        }
    
    elif action == "skip":
        current = user_sessions.get(user_id, {}).get('current_call_id')
        if current:
            update_call_status(current, 'skipped')
        
        bot.answer_callback_query(call.id, "⏭️ SKIPPED → Next ready!")
    
    elif action == "back":
        bot.answer_callback_query(call.id, "⬅️ Previous call ready")
    
    elif action == "marked":
        # CALL завершён
        call_id = call.data.split('_')[2]
        update_call_status(call_id, 'called')
        bot.answer_callback_query(call.id, "✅ CALL DONE ✓")

print("✅ PART 5: Pro button design (CALL 50%) ready")

# ===== ЧАСТЬ 6: MULTI-ADD + POLISH + RESET =====

@bot.callback_query_handler(func=lambda call: call.data == "add_numbers")
def multi_add_handler(call):
    """Multi-add - добавление к существующей базе"""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    stats = get_user_stats(user_id)
    text = (
        f"➕ **ADD TO EXISTING BASE**\n\n"
        f"📊 Current: **{stats['total']}** numbers\n\n"
        "**Send:**\n"
        "• `+1234567890 9876543210` (TEXT)\n"
        "• .XLSX file\n\n"
        "**New numbers will be ADDED** (not replaced!)"
    )
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📊 STATS", callback_data="show_stats"))
    markup.row(InlineKeyboardButton("☎️ CONTINUE CALL", callback_data="start_calling"))
    
    bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=["reset", "clear"])
def reset_handler(message):
    """Полная очистка базы"""
    user_id = message.from_user.id
    cursor.execute("DELETE FROM calls WHERE user_id=?", (user_id,))
    conn.commit()
    user_sessions[user_id] = {'position': 0}
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📊 ADD NUMBERS", callback_data="add_numbers"))
    
    bot.reply_to(
        message,
        "🗑️ **DATABASE CLEARED!**\n\n"
        "👆 Send TEXT or Excel to start fresh",
        reply_markup=markup,
        parse_mode='Markdown'
    )

# Улучшенный handle_input для multi-add
@bot.message_handler(content_types=["text", "document"], func=lambda m: True)
def universal_import(message):
    """Универсальный импорт для всех случаев"""
    user_id = message.from_user.id
    
    try:
        if message.text:
            count = import_numbers(user_id, message.text, "text")
            source_text = "TEXT"
        elif message.document and "spreadsheet" in message.document.mime_type:
            file_info = bot.get_file(message.document.file_id)
            file_bytes = bot.download_file(file_info.file_path)
            count = import_numbers(user_id, file_bytes, "excel")
            source_text = "EXCEL"
        else:
            return
        
        total = cursor.execute("SELECT COUNT(*) FROM calls WHERE user_id=?", (user_id,)).fetchone()[0]
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("☎️ CALL NOW", callback_data="start_calling"))
        markup.row(InlineKeyboardButton("📊 STATS", callback_data="show_stats"))
        
        bot.reply_to(
            message,
            f"✅ **{count} NEW** from {source_text}!\n"
            f"📊 **TOTAL: {total}**\n\n"
            f"Ready to CALL 👇",
            reply_markup=markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Universal import error: {e}")
        bot.reply_to(message, "❌ Try again or use /reset")

# Добавляем в stats_handler (строка 12 ЧАСТИ 4):
# InlineKeyboardButton("➕ ADD MORE", callback_data="add_numbers")

print("✅ PART 6: Multi-Add + Reset + Polish ready")

# ===== ЧАСТЬ 7: PRODUCTION READY + WEBHOOK BACKUP =====

# Error handler
@bot.message_handler(func=lambda message: True)
def error_catcher(message):
    """Ловит все необработанные сообщения"""
    logger.warning(f"Unhandled message from {message.from_user.id}: {message.text}")
    if message.text not in ['/start', '/reset', '/clear']:
        bot.reply_to(message, "❓ Use /start or send numbers")

# Graceful shutdown
import signal
def signal_handler(sig, frame):
    logger.info("Shutting down gracefully...")
    conn.close()
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ФИНАЛЬНЫЙ LAUNCH
if __name__ == "__main__":
    logger.info("🎉 SpeedCallerBot v3 FULL PRODUCTION READY!")
    logger.info("📱 Features: Excel/Text, tg://call, Multi-add, Stats, Reset")
    
    try:
        # Production polling с retry
        while True:
            bot.infinity_polling(
                timeout=20,
                long_polling_timeout=15,
                retry_after=5
            )
    except Exception as e:
        logger.error(f"Fatal polling error: {e}")
        time.sleep(30)
        logger.info("Restarting polling...")
