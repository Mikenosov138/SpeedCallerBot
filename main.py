print("=== BOT START ===")
import telebot
print("Telebot OK")
import os
print("OS OK")
import sqlite3
print("SQLite OK")
TOKEN = os.getenv("BOT_TOKEN")
print(f"TOKEN: {'OK' if TOKEN else 'MISSING'}")
import telebot
import os
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

# База данных
conn = sqlite3.connect("numbers.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS numbers (user_id INTEGER, number TEXT)")
conn.commit()

print("🚀 SpeedCaller Bot запущен!")

@bot.message_handler(commands=["start"])
def start(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📊 Загрузить Excel", callback_data="upload"))
    bot.send_message(message.chat.id, "🚀 SpeedCaller Bot готов!\n📊 Загрузи Excel с номерами.", reply_markup=markup)

@bot.message_handler(content_types=["document"])
def handle_doc(message):
    if message.document.mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        bot.reply_to(message, "📥 Обрабатываю...")
        # Здесь будет парсинг Excel (добавлю после теста)
        bot.send_message(message.chat.id, "✅ Excel загружен! Нажми Call для первого номера.")
    else:
        bot.reply_to(message, "❌ Только Excel файлы (.xlsx)")

bot.infinity_polling()
