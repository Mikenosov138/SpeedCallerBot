import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import openpyxl
import sqlite3
import os
import re

# # Secure token from Environment Variables
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    print("❌ BOT_TOKEN not found in Environment Variables!")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# # Database (phone as PRIMARY KEY, per user)
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS numbers 
                  (phone TEXT PRIMARY KEY, user_id INTEGER)''')
conn.commit()

def get_user_stats(user_id):
    """Get total count for user"""
    cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,))
    return cursor.fetchone()[0]

def get_next_phone(user_id):
    """Get next available phone (first unprocessed)"""
    cursor.execute("SELECT phone FROM numbers WHERE user_id=? LIMIT 1", (user_id,))
    return cursor.fetchone()

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    text = """🚀 Welcome to SpeedCaller Bot! 🤝🏻

For fast phone dialing and duplicate elimination.
Bot is COMPLETELY FREE!

📥 Upload phone database (text or Excel format)
📱 Numbers MUST start with '+' (11-13 chars total)

Press 📞 Call to start!"""
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📞 Call", callback_data="call"))
    markup.add(InlineKeyboardButton("➡️ Skip", callback_data="skip"))
    markup.add(InlineKeyboardButton("⚙️ Settings", callback_data="settings"))
    
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    if call.data == "call":
        total = get_user_stats(user_id)
        phone_result = get_next_phone(user_id)
        
        if phone_result and total > 0:
            phone = phone_result[0]
            current = total - cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,)).fetchone()[0] + 1
            text = f"""🚀 Welcome to SpeedCaller Bot!
💪🏻 Make speed calls

📊 Client: {current}/{total}
📱 Number: `{phone}`"""
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(InlineKeyboardButton("📞 CALL NOW", url=f"tel:{phone}"))
            markup.add(InlineKeyboardButton("➡️ Skip", callback_data="skip"))
            markup.add(InlineKeyboardButton("↩️ Back", callback_data="back"))
            
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode='Markdown')
        else:
            bot.answer_callback_query(call.id, "📭 No numbers! Upload database first.")
    
    elif call.data == "skip":
        cursor.execute("DELETE FROM numbers WHERE user_id=? LIMIT 1", (user_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ Skipped! Ready for next.")
        # # Delete message history
        bot.delete_message(chat_id, message_id)
        start(call.message)
    
    elif call.data == "back":
        # # Return to main menu (delete current)
        bot.delete_message(chat_id, message_id)
        start(call.message)
    
    elif call.data == "settings":
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("🧹 Clear Database", callback_data="clear"))
        markup.add(InlineKeyboardButton("➕ Add Database", callback_data="add_db"))
        markup.add(InlineKeyboardButton("📊 Stats", callback_data="stats"))
        markup.add(InlineKeyboardButton("↩️ Main Menu", callback_data="back"))
        
        bot.edit_message_text("⚙️ Settings:", chat_id, message_id, reply_markup=markup)
    
    elif call.data == "clear":
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "🧹 Database cleared!")
        bot.delete_message(chat_id, message_id)
        start(call.message)
    
    elif call.data == "add_db":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("↩️ Cancel", callback_data="back"))
        bot.send_message(chat_id, "➕ Upload text/Excel to ADD numbers to existing database:", reply_markup=markup)
    
    elif call.data == "stats":
        total = get_user_stats(user_id)
        bot.answer_callback_query(call.id, f"📊 Total numbers: {total}")

@bot.message_handler(content_types=['document', 'text'])
def handle_database(message):
    user_id = message.from_user.id
    
    try:
        imported_count = 0
        
        if message.document and message.document.file_name and message.document.file_name.lower().endswith('.xlsx'):
            # # Excel processing
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            with open('temp.xlsx', 'wb') as f:
                f.write(downloaded_file)
            
            wb = openpyxl.load_workbook('temp.xlsx')
            ws = wb.active
            
            for row in ws.iter_rows(min_row=1, values_only=True, max_col=1):
                if len(row) >= 1 and row[0]:
                    phone = clean_phone(str(row[0]).strip())
                    if phone:
                        cursor.execute("INSERT OR IGNORE INTO numbers (phone, user_id) VALUES (?, ?)",
                                     (phone, user_id))
                        imported_count += cursor.rowcount
            
            os.remove('temp.xlsx')
            
        elif message.text:
            # # Text processing (one message with numbers)
            for line in message.text.split('\n'):
                phone = clean_phone(line.strip())
                if phone:
                    cursor.execute("INSERT OR IGNORE INTO numbers (phone, user_id) VALUES (?, ?)",
                                 (phone, user_id))
                    imported_count += cursor.rowcount
        
        conn.commit()
        
        total = get_user_stats(user_id)
        bot.reply_to(message, f"✅ Added {imported_count} unique numbers!\n📊 Total: {total}\n📞 Press CALL!", 
                    reply_markup=get_main_markup())
        
        # # Delete original message
        bot.delete_message(message.chat.id, message.message_id)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)[:100]}")

def clean_phone(phone_str):
    """Validate and clean phone: + followed by 11-13 digits"""
    # # Extract only + and digits
    cleaned = re.sub(r'[^\+0-9]', '', phone_str)
    if cleaned.startswith('+') and len(cleaned) >= 12 and len(cleaned) <= 14:  # +11-13 digits
        return cleaned
    return None

def get_main_markup():
    """Main menu buttons"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📞 Call", callback_data="call"))
    markup.add(InlineKeyboardButton("➡️ Skip", callback_data="skip"))
    markup.add(InlineKeyboardButton("⚙️ Settings", callback_data="settings"))
    return markup

# # Infinite polling (non-stop)
print("🚀 SpeedCaller Bot started successfully!")
bot.infinity_polling(none_stop=True)
