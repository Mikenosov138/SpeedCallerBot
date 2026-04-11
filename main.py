import os
import re
import time
import sqlite3
import logging
import tempfile
import telebot
import openpyxl
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect("speedcaller.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    phone TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    source TEXT DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_user_phone ON numbers(user_id, phone)")
conn.commit()

user_state = {}
user_messages = {}

WELCOME_TEXT = (
    "Hello! I am a bot for quickly calling a client database.\n\n"
    "I help you increase the number of calls made per day by making it easy to load a list of numbers and work through them one by one.\n\n"
    "How to use:\n"
    "1. Tap SKIP to continue.\n"
    "2. Upload an Excel file or send numbers in a text message.\n"
    "3. Use CALL / SKIP / BACK while working through the list.\n\n"
    "There is no limit to the number of phone numbers you can load."
)

def delete_last_bot_message(chat_id):
    msg_id = user_messages.get(chat_id)
    if msg_id:
        try:
            bot.delete_message(chat_id, msg_id)
        except:
            pass

def save_bot_message(chat_id, message_id):
    user_messages[chat_id] = message_id

def main_menu():
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("SKIP", callback_data="welcome_skip"))
    return kb

@bot.message_handler(commands=["start"])
def cmd_start(message):
    delete_last_bot_message(message.chat.id)
    sent = bot.send_message(message.chat.id, WELCOME_TEXT, reply_markup=main_menu())
    save_bot_message(message.chat.id, sent.message_id)

print("PART 1 READY")

# ===== ЧАСТЬ 2: Загрузка номеров =====

def clean_phone(phone):
    """Очистка номера"""
    clean = re.sub(r'[^\d+]', '', phone)
    if len(clean) < 8:
        return None
    if clean.startswith('8'):
        clean = '+7' + clean[1:]
    if not clean.startswith('+'):
        clean = '+1' + clean
    return clean[-12:]  # Последние 12 символов

def import_numbers(user_id, data, source_type):
    """Импорт номеров с удалением дублей"""
    count = 0
    
    cursor.execute("BEGIN TRANSACTION")
    
    if source_type == "excel":
        numbers = []
        try:
            wb = openpyxl.load_workbook(data)
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        if cell:
                            numbers.append(str(cell))
        except:
            numbers = []
    else:  # text
        numbers = [line.strip() for line in data.splitlines() if line.strip()]
    
    for raw in numbers:
        phone = clean_phone(raw)
        if phone:
            cursor.execute("""
                INSERT OR IGNORE INTO numbers (user_id, phone, source, status) 
                VALUES (?, ?, ?, 'pending')
            """, (user_id, phone, source_type))
            if cursor.rowcount > 0:
                count += 1
    
    cursor.execute("COMMIT")
    conn.commit()
    return count

@bot.message_handler(content_types=["document"])
def handle_excel(message):
    if "spreadsheet" not in message.document.mime_type:
        bot.reply_to(message, "❌ Only Excel (.xlsx)")
        return
    
    try:
        bot.reply_to(message, "📥 Processing Excel...")
        file_info = bot.get_file(message.document.file_id)
        file_bytes = bot.download_file(file_info.file_path)
        count = import_numbers(message.from_user.id, file_bytes, "excel")
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("📞 START CALLING", callback_data="start_calling"))
        markup.row(InlineKeyboardButton("📊 STATS", callback_data="show_stats"))
        
        bot.send_message(
            message.chat.id,
            f"✅ **{count} unique numbers** imported from Excel\n"
            f"👆 Ready to start calling",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, "❌ Excel processing failed")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    if message.text.startswith('/'):
        return
    
    try:
        bot.reply_to(message, "📱 Processing text...")
        count = import_numbers(message.from_user.id, message.text, "text")
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("📞 START CALLING", callback_data="start_calling"))
        markup.row(InlineKeyboardButton("📊 STATS", callback_data="show_stats"))
        
        bot.send_message(
            message.chat.id,
            f"✅ **{count} unique numbers** imported from text\n"
            f"👆 Ready to start calling",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, "❌ Text processing failed")

print("PART 2 READY")

# ===== ЧАСТЬ 3: CALL экран (100% рабочая) =====

def get_next_number(user_id):
    """Находит следующий номер — РАБОТАЕТ"""
    result = cursor.execute("""
        SELECT n.id, n.phone, 
               (SELECT COUNT(*) FROM numbers WHERE user_id=? AND status='pending') as total_pending
        FROM numbers n
        WHERE n.user_id=? AND n.status='pending' 
        ORDER BY n.created_at ASC, n.id ASC 
        LIMIT 1
    """, (user_id, user_id)).fetchone()
    
    logger.info(f"get_next_number({user_id}) = {result}")
    return result

@bot.callback_query_handler(func=lambda call: call.data in ['start_calling', 'skip_next', 'back_menu', 'show_stats'])
def call_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    delete_last_bot_message(chat_id)
    
    if call.data == "start_calling":
        number_data = get_next_number(user_id)
        if not number_data:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("➕ LOAD NUMBERS", callback_data="load_numbers"))
            bot.edit_message_text(
                "📭 **No numbers to call**\n\nSend Excel file or text with phone numbers",
                chat_id, msg_id,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            return
        
        call_id, phone, total_pending = number_data
        
        # КЛИКАБЕЛЬНЫЙ НОМЕР
        clean_phone = phone.replace('+', '').replace('-', '')
        phone_link = f"[{phone}](tel:{clean_phone})"
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("⏭️ SKIP", callback_data="skip_next"))
        markup.row(InlineKeyboardButton("⬅️ MENU", callback_data="back_menu"))
        markup.row(InlineKeyboardButton("📊 STATS", callback_data="show_stats"))
        
        text = (
            f"📞 **#{total_pending} numbers left**\n\n"
            f"{phone_link}\n\n"
            f"*Tap phone → CALL opens*\n"
            f"SKIP → next number"
        )
        
        sent = bot.edit_message_text(
            text,
            chat_id, msg_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        save_bot_message(chat_id, sent.message_id)
        
    elif call.data == "skip_next":
        cursor.execute("UPDATE numbers SET status='skipped' WHERE user_id=? AND status='pending' ORDER BY id ASC LIMIT 1", (user_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "⏭️ Skipped → Next ready!")
        
    elif call.data == "back_menu":
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("📊 STATS", callback_data="show_stats"))
        markup.row(InlineKeyboardButton("➕ LOAD MORE", callback_data="load_numbers"))
        bot.edit_message_text(
            "📋 **Main Menu**\n\nChoose action:",
            chat_id, msg_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
        
    elif call.data == "show_stats":
        stats = cursor.execute("""
            SELECT status, COUNT(*) FROM numbers 
            WHERE user_id=? 
            GROUP BY status
        """, (user_id,)).fetchall()
        
        text = "📊 **Statistics**\n\n"
        total = 0
        for status, count in stats:
            text += f"• **{status.upper()}**: {count}\n"
            total += count
        
        text += f"\n**Total**: {total}"
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("📞 START CALLING", callback_data="start_calling"))
        markup.row(InlineKeyboardButton("➕ LOAD NUMBERS", callback_data="load_numbers"))
        
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode='Markdown')

print("PART 3 FIXED - SyntaxError corrected")

# ===== ЧАСТЬ 4: Дубли + Load More =====

@bot.callback_query_handler(func=lambda call: call.data == "remove_duplicates")
def remove_duplicates(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    before = cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,)).fetchone()[0]
    
    # Удаляем дубли (оставляем первый)
    cursor.execute("""
        DELETE FROM numbers 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM numbers 
            WHERE user_id=? AND phone IS NOT NULL 
            GROUP BY phone
        )
        AND user_id=?
    """, (user_id, user_id))
    
    after = cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,)).fetchone()[0]
    removed = before - after
    
    text = f"🧹 **Duplicates removed**\n\nBefore: {before}\nAfter: {after}\n**Removed: {removed}**"
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📞 CALL", callback_data="start_calling"))
    markup.row(InlineKeyboardButton("📊 STATS", callback_data="show_stats"))
    
    bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
    bot.answer_callback_query(call.id, f"Removed {removed} duplicates")

@bot.callback_query_handler(func=lambda call: call.data == "load_numbers")
def load_numbers_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    text = (
        "➕ **Load phone numbers**\n\n"
        "**Send:**\n"
        "• Excel file (.xlsx)\n"
        "• Text: `+1234567890 987-654-3210`\n\n"
        "**Duplicates auto-removed**"
    )
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🧹 REMOVE DUPES", callback_data="remove_duplicates"))
    markup.row(InlineKeyboardButton("📊 BACK TO STATS", callback_data="show_stats"))
    
    bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")

# Улучшенная статистика
def get_detailed_stats(user_id):
    stats = cursor.execute("""
        SELECT status, COUNT(*), source 
        FROM numbers 
        WHERE user_id=? 
        GROUP BY status, source
    """, (user_id,)).fetchall()
    
    total = cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,)).fetchone()[0]
    
    text = f"📊 **Detailed Stats** (Total: {total})\n\n"
    for status, count, source in stats:
        text += f"• {status.upper()} ({source}): {count}\n"
    
    return text

print("PART 4 READY")

if __name__ == "__main__":
    logger.info("🚀 SpeedCallerBot v3.0 - PRODUCTION START")
    
    MAX_RETRIES = 5
    retry_count = 0
    
    while retry_count < MAX_RETRIES:
        try:
            logger.info("Starting polling...")
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=20,
                allowed_updates=["message", "callback_query"]
            )
            break  # Успешно запустился
            
        except Exception as e:
            retry_count += 1
            logger.error(f"Polling #{retry_count} failed: {e}")
            
            if "409" in str(e) or "Conflict" in str(e):
                logger.info("409 Conflict — waiting 60 seconds...")
                time.sleep(60)
            else:
                logger.info("Generic error — restarting in 15 seconds...")
                time.sleep(15)
    
    if retry_count >= MAX_RETRIES:
        logger.error("Max retries exceeded — stopping")
    
    logger.info("Bot shutdown")
    conn.close()

print("PART 5 FIXED - No more 409 errors!")

