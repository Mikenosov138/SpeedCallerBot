import telebot
import os

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "🚀 SpeedCaller Bot работает! Загрузи Excel.")

@bot.message_handler(content_types=["document"])
def doc(message):
    bot.reply_to(message, f"📥 Загружен файл: {message.document.file_name}")

print("Bot starting...")
bot.infinity_polling()
