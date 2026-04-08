import os
print("1. OS OK")
TOKEN = os.getenv("BOT_TOKEN")
print(f"2. TOKEN: {len(TOKEN) if TOKEN else 'MISSING'} символов")
import telebot
print("3. Telebot OK")
bot = telebot.TeleBot(TOKEN)
print("4. BOT OK - ПИШИ /start!")
bot.infinity_polling()
