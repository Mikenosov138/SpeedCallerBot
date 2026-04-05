import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import openpyxl
import sqlite3
import os
import re
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logger.error("BOT_TOKEN not found in environment variables")
    raise SystemExit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    phone TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, phone)
)
""")
conn.commit()

def normalize_phone(value):
    if value is None:
        return None
    s = str(value).strip().replace(" ", "")
    if not s:
        return None
    s = re.sub(r"[^\d+]", "", s)
    if s.startswith("+"):
        digits = s[1:]
    else:
        digits = s
        s = "+" + s
    if not digits.isdigit():
        return None
    if not (10 <= len(digits) <= 13):
        return None
    return s

def get_total_numbers(user_id):
    cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

def get_first_number(user_id):
    cursor.execute("SELECT id, phone FROM numbers WHERE user_id=? ORDER BY id ASC LIMIT 1", (user_id,))
    return cursor.fetchone()

def delete_first_number(user_id):
    cursor.execute(
        "DELETE FROM numbers WHERE id = (SELECT id FROM numbers WHERE user_id=? ORDER BY id ASC LIMIT 1)",
        (user_id,)
    )
    conn.commit()

def clear_user_numbers(user_id):
    cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
    conn.commit()

def get_main_markup():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📞 Call", callback_data="call"),
        InlineKeyboardButton("➡️ Skip", callback_data="skip"),
        InlineKeyboardButton("⚙️ Settings", callback_data="settings")
    )
    return markup

def get_settings_markup():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🧹 Clear Database", callback_data="clear_db"),
        InlineKeyboardButton("➕ Add Database", callback_data="add_db"),
        InlineKeyboardButton("📊 Stats", callback_data="stats"),
        InlineKeyboardButton("↩️ Back", callback_data="back")
    )
    return markup

def get_call_markup(phone):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📞 CALL NOW", url=f"tel:{phone}"),
        InlineKeyboardButton("➡️ Skip", callback_data="skip"),
        InlineKeyboardButton("↩️ Back", callback_data="back")
    )
    return markup

def send_welcome(chat_id):
    text = (
        "🚀 Welcome to SpeedCaller Bot! 🤝🏻\n\n"
        "For fast phone dialing and duplicate elimination.\n"
        "Bot is COMPLETELY FREE!\n\n"
        "📥 Upload phone database (text or Excel format)\n"
        "📱 Numbers can start with '+' or without it\n\n"
        "👆 Press 📞 Call to start!"
    )
    bot.send_message(chat_id, text, reply_markup=get_main_markup())

@bot.message_handler(commands=["start", "help"])
def start_handler(message):
    try:
        send_welcome(message.chat.id)
        logger.info(f"User {message.from_user.id} started the bot")
    except Exception as e:
        logger.exception(f"Error in start_handler: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass

    try:
        if call.data == "call":
            total = get_total_numbers(user_id)
            first = get_first_number(user_id)

            if not first:
                bot.send_message(
                    chat_id,
                    "📭 No numbers in database.\n\nUpload database first!",
                    reply_markup=get_main_markup()
                )
                return

            _, phone = first
            text = (
                "🚀 Welcome to SpeedCaller Bot!\n"
                "💪🏻 Make speed calls\n\n"
                f"📊 Client: 1/{total}\n"
                f"📱 Number: `{phone}`"
            )
            bot.send_message(chat_id, text, reply_markup=get_call_markup(phone))

        elif call.data == "skip":
            delete_first_number(user_id)
            total = get_total_numbers(user_id)
            first = get_first_number(user_id)

            if first:
                _, phone = first
                text = (
                    "🚀 Welcome to SpeedCaller Bot!\n"
                    "💪🏻 Make speed calls\n\n"
                    f"📊 Client: 1/{total}\n"
                    f"📱 Number: `{phone}`"
                )
                bot.send_message(chat_id, text, reply_markup=get_call_markup(phone))
            else:
                bot.send_message(
                    chat_id,
                    "✅ Skipped!\n\n📭 Database is empty now.",
                    reply_markup=get_main_markup()
                )

        elif call.data == "back":
            send_welcome(chat_id)

        elif call.data == "settings":
            bot.send_message(chat_id, "⚙️ Settings:", reply_markup=get_settings_markup())

        elif call.data == "clear_db":
            clear_user_numbers(user_id)
            bot.send_message(chat_id, "🧹 Database cleared!", reply_markup=get_main_markup())

        elif call.data == "add_db":
            text = (
                "➕ Upload text/Excel to ADD numbers to existing database.\n\n"
                "Numbers without '+' will be accepted and automatically converted."
            )
            bot.send_message(chat_id, text, reply_markup=get_settings_markup())

        elif call.data == "stats":
            total = get_total_numbers(user_id)
            bot.send_message(chat_id, f"📊 Total unique numbers: `{total}`", reply_markup=get_settings_markup())

    except Exception as e:
        logger.exception(f"Error in callback_handler: {e}")
        try:
            bot.send_message(chat_id, "❌ Something went wrong.", reply_markup=get_main_markup())
        except:
            pass

@bot.message_handler(content_types=["document", "text"])
def handle_upload(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    imported_count = 0

    try:
        if message.content_type == "document":
            filename = message.document.file_name.lower() if message.document.file_name else ""
            if not filename.endswith(".xlsx"):
                bot.send_message(chat_id, "❌ Please upload only .xlsx Excel files or text with phone numbers.", reply_markup=get_main_markup())
                return

            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)

            temp_name = f"temp_{user_id}.xlsx"
            with open(temp_name, "wb") as f:
                f.write(downloaded)

            wb = openpyxl.load_workbook(temp_name, data_only=True)
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        phone = normalize_phone(cell)
                        if phone:
                            cursor.execute(
                                "INSERT OR IGNORE INTO numbers (user_id, phone) VALUES (?, ?)",
                                (user_id, phone)
                            )
                            imported_count += cursor.rowcount

            try:
                os.remove(temp_name)
            except:
                pass

        elif message.content_type == "text":
            text = message.text.strip()
            for line in text.splitlines():
                phone = normalize_phone(line)
                if phone:
                    cursor.execute(
                        "INSERT OR IGNORE INTO numbers (user_id, phone) VALUES (?, ?)",
                        (user_id, phone)
                    )
                    imported_count += cursor.rowcount

        conn.commit()
        total = get_total_numbers(user_id)

        bot.send_message(
            chat_id,
            f"✅ Success! Imported {imported_count} unique numbers.\n📊 Total: {total}\n📞 Press CALL to start!",
            reply_markup=get_main_markup()
        )

    except Exception as e:
        logger.exception(f"Upload error: {e}")
        try:
            bot.send_message(chat_id, f"❌ Upload error: {str(e)[:150]}", reply_markup=get_main_markup())
        except:
            pass

@bot.message_handler(func=lambda m: True)
def fallback_handler(message):
    try:
        bot.send_message(message.chat.id, "❓ Use /start or the buttons below.", reply_markup=get_main_markup())
    except:
        pass

def main():
    logger.info("SpeedCaller bot is starting polling...")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
        except Exception as e:
            logger.exception(f"Polling crashed: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
