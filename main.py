#!/usr/bin/env python3
print("=== 0. SHEBANG OK ===")
import os
print("1. OS OK")
TOKEN = os.getenv("BOT_TOKEN")
print(f"2. TOKEN: {len(TOKEN) if TOKEN else 'MISSING'} symbols")
import telebot
print("3. Telebot OK")
bot = telebot.TeleBot(TOKEN)
print("4. BOT OK - Send /start!")

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "✅ SpeedCallerBot is LIVE!")

print("5. HANDLER OK - STARTING POLLING...")
bot.infinity_polling()
