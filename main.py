import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import openpyxl
import sqlite3
import os

TOKEN = '8539274936:AAFy9Rw1FKEKIseQNxtNDXdgJjxFsXuWUhg'  # Замени на реальный!
bot = telebot.TeleBot(TOKEN)

# БД
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS numbers (phone TEXT, name TEXT, note TEXT, user_id INTEGER)''')
conn.commit()

@bot.message_handler(commands=['start'])
def start(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📞 Call", callback_data="call"))
    markup.add(InlineKeyboardButton("➡️ Skip", callback_data="skip"))
    markup.add(InlineKeyboardButton("⚙️ Settings", callback_data="settings"))
    bot.send_message(message.chat.id, "🚀 SpeedCaller готов! Загрузи Excel для базы.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data == "call":
        cursor.execute("SELECT phone FROM numbers WHERE user_id=? LIMIT 1", (call.from_user.id,))
        phone = cursor.fetchone()
        if phone:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📞 Позвонить", url=f"tel:{phone[0]}"))
            markup.add(InlineKeyboardButton("➡️ Skip", callback_data="skip"))
            bot.edit_message_text("📞 Номер для звонка:", call.message.chat.id, call.message.id, reply_markup=markup)
    elif call.data == "skip":
        bot.answer_callback_query(call.id, "Скип!")
        # Логика скипа
    bot.answer_callback_query(call.id)

@bot.message_handler(content_types=['document'])
def handle_doc(message):
    if message.document.mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        wb = openpyxl.load_workbook(file_info=file_info.file_path.encode())
        # Парсинг Excel в БД
        bot.reply_to(message, "✅ База загружена!")

print("SpeedCaller запущен!")
bot.polling(none_stop=True)
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
