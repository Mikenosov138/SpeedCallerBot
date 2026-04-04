import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import openpyxl
import sqlite3
import os

# # Replace with your bot token from BotFather # Добавь в импорты (строка 5)

# ПРАВИЛЬНО (безопасно)
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    print("❌ BOT_TOKEN not found! Add to Render Environment Variables")
    exit(1)
bot = telebot.TeleBot(TOKEN)

# # Database connection (SQLite - per-user numbers)
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS numbers 
                  (phone TEXT PRIMARY KEY, name TEXT, note TEXT, user_id INTEGER)''')
conn.commit()

@bot.message_handler(commands=['start'])
def start(message):
    # # English greeting + upload request
    text = """
🚀 Welcome to SpeedCaller Bot!

Upload Excel file (.xlsx) with columns:
📱 Phone | 👤 Name | 📝 Note

Example:
+79123456789 | John | Lead from ad

Press 📞 Call to start!
    """
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📞 Call", callback_data="call"))
    markup.add(InlineKeyboardButton("➡️ Skip", callback_data="skip"))
    markup.add(InlineKeyboardButton("⚙️ Settings", callback_data="settings"))
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    
    if call.data == "call":
        # # Get next phone for user
        cursor.execute("SELECT phone, name FROM numbers WHERE user_id=? ORDER BY rowid LIMIT 1", (user_id,))
        result = cursor.fetchone()
        
        if result:
            phone, name = result
            text = f"📞 Call #{name or 'Unknown'}\n📱 {phone}"
            
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("📞 CALL NOW", url=f"tel:{phone}"))
            markup.add(InlineKeyboardButton("➡️ Skip", callback_data="skip"))
            markup.add(InlineKeyboardButton("↩️ Back", callback_data="back"))
            
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, 
                                reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "📭 No numbers in database. Upload Excel!")
    
    elif call.data == "skip":
        # # Mark as processed (delete first number)
        cursor.execute("DELETE FROM numbers WHERE user_id=? LIMIT 1", (user_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ Skipped! Next number ready.")
        # # Refresh call button
        start(call.message)
    
    elif call.data == "back":
        start(call.message)
    
    elif call.data == "settings":
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("🧹 Clear Database", callback_data="clear"))
        markup.add(InlineKeyboardButton("📊 Stats", callback_data="stats"))
        markup.add(InlineKeyboardButton("↩️ Main Menu", callback_data="back"))
        bot.edit_message_text("⚙️ Settings:", call.message.chat.id, call.message.message_id, 
                            reply_markup=markup)
    
    elif call.data == "clear":
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "🧹 Database cleared!")
    
    elif call.data == "stats":
        cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,))
        count = cursor.fetchone()[0]
        bot.answer_callback_query(call.id, f"📊 Numbers in DB: {count}")

@bot.message_handler(content_types=['document'])
def handle_excel(message):
    user_id = message.from_user.id
    
    # # Check Excel file
    if not message.document.file_name or not message.document.file_name.lower().endswith('.xlsx'):
        bot.reply_to(message, "❌ Please upload .xlsx file only!")
        return
    
    try:
        # # Download file
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # # Save temporarily
        with open('temp.xlsx', 'wb') as f:
            f.write(downloaded_file)
        
        # # Parse Excel (columns: Phone, Name, Note)
        wb = openpyxl.load_workbook('temp.xlsx')
        ws = wb.active
        
        # # Clear old data for user
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        
        imported_count = 0
        for row in ws.iter_rows(min_row=2, values_only=True, max_col=3):  # First 3 columns
            if len(row) >= 1 and row[0] and str(row[0]).startswith('+'):  # Valid phone
                phone = str(row[0]).strip()
                name = str(row[1]).strip() if len(row) > 1 and row[1] else "Unknown"
                note = str(row[2]).strip() if len(row) > 2 and row[2] else ""
                
                # # Remove duplicates
                cursor.execute("INSERT OR IGNORE INTO numbers (phone, name, note, user_id) VALUES (?, ?, ?, ?)",
                             (phone, name, note, user_id))
                imported_count += cursor.rowcount
        
        conn.commit()
        
        # # Cleanup
        os.remove('temp.xlsx')
        
        bot.reply_to(message, f"✅ Success! Imported {imported_count} unique numbers.\n📞 Press CALL to start!")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Upload error: {str(e)[:100]}")
        if os.path.exists('temp.xlsx'):
            os.remove('temp.xlsx')

# # Start bot (non-stop)
print("🚀 SpeedCaller Bot started!")
bot.infinity_polling(none_stop=True)
