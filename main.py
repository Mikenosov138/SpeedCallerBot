import os
import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect("numbers.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS numbers (user_id INTEGER, number TEXT, status TEXT DEFAULT 'pending')")
conn.commit()

user_positions = {}

@bot.message_handler(commands=["start"])
def start(message):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📊 Demo Numbers", callback_data="demo"))
    markup.row(InlineKeyboardButton("📈 Stats", callback_data="stats"))
    bot.send_message(message.chat.id, "✅ SpeedCallerBot v2 READY!\n👇 Load demo or upload Excel", reply_markup=markup)

@bot.message_handler(content_types=["document"])
def handle_doc(message):
    bot.reply_to(message, "✅ Demo mode: 150 numbers loaded!\nClick CALL 👇")

@bot.callback_query_handler(func=lambda call: True)
def callback(call: CallbackQuery):
    user_id = call.from_user.id
    
    if call.data == "demo":
        cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
        for i in range(150):
            cursor.execute("INSERT INTO numbers (user_id, number, status) VALUES (?, ?, 'pending')",
                          (user_id, f"+1-555-{i:03d}-{i:04d}"))
        conn.commit()
        bot.edit_message_text("✅ 150 demo numbers loaded!\nClick CALL 👇", 
                            call.message.chat.id, call.message.id)
    
    elif call.data == "stats":
        stats = cursor.execute("SELECT status, COUNT(*) FROM numbers WHERE user_id=? GROUP BY status", (user_id,)).fetchall()
        text = "📈 Stats:\n" + "\n".join([f"{s}: {c}" for s,c in stats]) if stats else "📭 No data"
        bot.edit_message_text(text, call.message.chat.id, call.message.id)
    
    elif call.data == "call":
        numbers = cursor.execute("SELECT rowid, number FROM numbers WHERE user_id=? AND status='pending' ORDER BY rowid LIMIT 100", (user_id,)).fetchall()
        if not numbers:
            bot.edit_message_text("📭 No numbers. Load demo first!", call.message.chat.id, call.message.id)
            return
        
        pos = user_positions.get(user_id, 0) % len(numbers)
        rowid, number = numbers[pos]
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("☎️ CALL", callback_data="call"), InlineKeyboardButton("⏭️ Skip", callback_data="skip"))
        markup.row(InlineKeyboardButton("⬅️ Back", callback_data="back"), InlineKeyboardButton("📊 Stats", callback_data="stats"))
        
        bot.edit_message_text(f"📞 #{pos+1} of {len(numbers)}\n\n<code>{number}</code>", 
                            call.message.chat.id, call.message.id, 
                            reply_markup=markup, parse_mode='HTML')
        user_positions[user_id] = pos
    
    elif call.data == "skip":
        pos = user_positions.get(user_id, 0)
        numbers = cursor.execute("SELECT rowid FROM numbers WHERE user_id=? AND status='pending' ORDER BY rowid LIMIT 100", (user_id,)).fetchall()
        if numbers:
            rowid = numbers[pos % len(numbers)][0]
            cursor.execute("UPDATE numbers SET status='skipped' WHERE rowid=?", (rowid,))
            conn.commit()
        user_positions[user_id] = (user_positions.get(user_id, 0) + 1) % 100
        bot.answer_callback_query(call.id, "Skipped ✅")
    
    elif call.data == "back":
        user_positions[user_id] = max(0, user_positions.get(user_id, 0) - 1)
        bot.answer_callback_query(call.id, "Back ⬅️")
    
    bot.answer_callback_query(call.id)

print("🚀 SpeedCallerBot v2 DEMO starting...")
bot.infinity_polling(timeout=10)
