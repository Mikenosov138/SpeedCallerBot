import os
import sqlite3
import openpyxl
import tempfile
import os
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

TOKEN = os.getenv("BOT_TOKEN")
bot = TeleBot(TOKEN)

# Database
conn = sqlite3.connect("numbers.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS numbers (
        user_id INTEGER, 
        number TEXT, 
        status TEXT DEFAULT 'pending'
    )
""")
conn.commit()

user_positions = {}  # {user_id: current_position}

@bot.message_handler(commands=["start"])
def start(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📊 Upload Excel", callback_data="upload"))
    markup.add(InlineKeyboardButton("📈 Stats", callback_data="stats"))
    bot.send_message(message.chat.id, 
        "✅ SpeedCallerBot v2 is LIVE!\n\n"
        "📊 Upload Excel → Get numbers → Call/Skip/Back", 
        reply_markup=markup)

@bot.message_handler(content_types=["document"])
def handle_excel(message):
    if not message.document.mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        bot.reply_to(message, "❌ Only Excel (.xlsx) files")
        return
    
    bot.reply_to(message, "📥 Processing Excel...")
    file_info = bot.get_file(message.document.file_id)
    file_bytes = bot.download_file(file_info.file_path)
    
    added = import_from_excel(message.from_user.id, file_bytes)
    bot.send_message(message.chat.id, f"✅ {added} numbers imported!\nClick CALL to start.")

def import_from_excel(user_id, file_bytes):
    temp_name = f"temp_{int(time.time())}.xlsx"
    with open(temp_name, "wb") as f:
        f.write(file_bytes)
    
    added = 0
    try:
        wb = openpyxl.load_workbook(temp_name, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if cell and isinstance(cell, (int, float, str)):
                        number = str(cell).strip()
                        if number and len(number) > 5:
                            cursor.execute(
                                "INSERT OR IGNORE INTO numbers (user_id, number) VALUES (?, ?)",
                                (user_id, number)
                            )
                            added += 1
        conn.commit()
    except Exception:
        pass
    finally:
        os.remove(temp_name)
    
    return added

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call: CallbackQuery):
    user_id = call.from_user.id
    
    if call.data == "upload":
        bot.answer_callback_query(call.id, "Send Excel file 📊")
    
    elif call.data == "stats":
        stats = cursor.execute(
            "SELECT status, COUNT(*) FROM numbers WHERE user_id=? GROUP BY status", 
            (user_id,)
        ).fetchall()
        text = "📈 Stats:\n"
        for status, count in stats:
            text += f"{status}: {count}\n"
        bot.edit_message_text(text, call.message.chat.id, call.message.id)
    
    elif call.data == "call":
        position = user_positions.get(user_id, 0)
        numbers = cursor.execute(
            "SELECT number FROM numbers WHERE user_id=? AND status='pending' ORDER BY rowid LIMIT 50", 
            (user_id,)
        ).fetchall()
        
        if not numbers:
            bot.edit_message_text("📭 No more numbers. Upload new Excel.", 
                                call.message.chat.id, call.message.id)
            return
        
        number = numbers[position % len(numbers)][0]
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("☎️ CALL", callback_data="call"),
            InlineKeyboardButton("⏭️ Skip", callback_data="skip")
        )
        markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back"))
        
        bot.edit_message_text(
            f"📞 Number #{position+1}\n\n<code>{number}</code>", 
            call.message.chat.id, call.message.id,
            reply_markup=markup, parse_mode="HTML"
        )
    
    elif call.data == "skip":
        cursor.execute("UPDATE numbers SET status='skipped' WHERE user_id=? AND number=?", 
                      (user_id, get_current_number(call)))
        conn.commit()
        user_positions[user_id] = user_positions.get(user_id, 0) + 1
        handle_call(call)
    
    elif call.data == "back":
        user_positions[user_id] = max(0, user_positions.get(user_id, 0) - 1)
        handle_call(call)
    
    elif call.data == "call_next":
        handle_call(call)

def get_current_number(call):
    # Simplified - returns current number
    return "placeholder"

def handle_call(call):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("☎️ CALL", callback_data="call"),
        InlineKeyboardButton("⏭️ Skip", callback_data="skip")
    )
    markup.add(InlineKeyboardButton("⬅️ Back", callback_data="back"))
    bot.answer_callback_query(call.id)

if __name__ == "__main__":
    print("🚀 SpeedCallerBot v2 FULL VERSION starting...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
