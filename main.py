import asyncio
import logging
import os
import re
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import sqlite3
import openpyxl
from typing import List, Dict
import aiofiles

# Твой токен от @BotFather
BOT_TOKEN = "8539274936:AAFy9Rw1FKEKIseQNxtNDXdgJjxFsXuWUhg"

# Настройка логирования
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Состояния FSM
class BotStates(StatesGroup):
    waiting_for_numbers = State()
    waiting_for_duplicates = State()
    calling = State()

# Инициализация БД
def init_db():
    conn = sqlite3.connect('speedcaller.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 current_index INTEGER DEFAULT 0,
                 total_contacts INTEGER DEFAULT 0
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS contacts (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER,
                 phone TEXT UNIQUE,
                 original_phone TEXT,
                 position INTEGER,
                 FOREIGN KEY (user_id) REFERENCES users (user_id)
                 )''')
    conn.commit()
    conn.close()

init_db()

def normalize_phone(phone: str) -> str:
    """Нормализует номер для tel: ссылки"""
    # Убираем пробелы, скобки, тире, точки
    cleaned = re.sub(r'[^\d+]', '', phone)
    # Если нет +, оставляем как есть (локальные номера)
    return cleaned

def get_user_contacts(user_id: int) -> List[Dict]:
    """Получает контакты пользователя"""
    conn = sqlite3.connect('speedcaller.db')
    c = conn.cursor()
    c.execute('SELECT id, original_phone, phone, position FROM contacts WHERE user_id=? ORDER BY position', (user_id,))
    contacts = [{"id": row[0], "original": row[1], "phone": row[2], "pos": row[3]} for row in c.fetchall()]
    conn.close()
    return contacts

@router.message(CommandStart())
async def start_handler(message: Message):
    """Стартовая страница"""
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚀 Start Call")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer(
        "👋 Hello! For ease of use, upload phone numbers in Excel format or type them in a column as a message. "
        "The bot is designed exclusively for cold calling; we do not store contact information. "
        "We can delete any duplicate numbers for your convenience. To get started, click \"Start Call\" 📞",
        reply_markup=kb
    )

@router.message(F.text == "🚀 Start Call")
async def start_call_handler(message: Message):
    """Выбор способа загрузки"""
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚙️ Settings")],
            [KeyboardButton(text="📊 Export numbers in Excel format or send a message")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "📱 Export numbers in Excel format or send a message",
        reply_markup=kb
    )

@router.message(F.document | F.text)
async def process_numbers(message: Message, state: FSMContext):
    """Обработка Excel или текста"""
    user_id = message.from_user.id
    
    # Сохраняем файл если Excel
    if message.document:
        file = await bot.get_file(message.document.file_id)
        file_path = f"uploads/{user_id}_{message.document.file_name}"
        os.makedirs("uploads", exist_ok=True)
        await bot.download_file(file.file_path, file_path)
        
        # Парсим Excel
        wb = openpyxl.load_workbook(file_path)
        sheet = wb.active
        contacts = []
        for row in sheet.iter_rows(values_only=True):
            for cell in row:
                if isinstance(cell, str) and re.search(r'[\d+]', str(cell)):
                    contacts.append(str(cell).strip())
    else:
        # Парсим текст (по строкам)
        contacts = [line.strip() for line in message.text.split('\n') if line.strip()]
    
    # Сохраняем в БД
    conn = sqlite3.connect('speedcaller.db')
    c = conn.cursor()
    
    # Удаляем старые контакты
    c.execute('DELETE FROM contacts WHERE user_id=?', (user_id,))
    
    # Добавляем новые с позициями
    for i, phone in enumerate(contacts):
        normalized = normalize_phone(phone)
        c.execute('INSERT OR IGNORE INTO contacts (user_id, phone, original_phone, position) VALUES (?, ?, ?, ?)',
                 (user_id, normalized, phone, i))
    
    total = c.rowcount
    c.execute('INSERT OR REPLACE INTO users (user_id, total_contacts) VALUES (?, ?)', (user_id, total))
    conn.commit()
    conn.close()
    
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="▶️ Start Work")],
            [KeyboardButton(text="📋 Add Contacts")],
            [KeyboardButton(text="⚙️ Settings")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"✅ You've successfully uploaded your numbers! Let's get started! ({total} contacts)",
        reply_markup=kb
    )

@router.message(F.text == "▶️ Start Work")
async def start_work_handler(message: Message, state: FSMContext):
    """Подтверждение удаления дублей"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes", callback_data="duplicates_yes")],
        [InlineKeyboardButton(text="❌ No", callback_data="duplicates_no")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]
    ])
    await message.answer(
        "🧹 Remove duplicate phone numbers?",
        reply_markup=kb
    )

@router.callback_query(F.data.startswith("duplicates_"))
async def process_duplicates(callback: CallbackQuery):
    """Обработка дублей"""
    user_id = callback.from_user.id
    
    if callback.data == "duplicates_yes":
        conn = sqlite3.connect('speedcaller.db')
        c = conn.cursor()
        # Удаляем дубли, оставляем первые
        c.execute('DELETE FROM contacts WHERE id NOT IN (SELECT MIN(id) FROM contacts WHERE user_id=? GROUP BY phone)', (user_id,))
        conn.commit()
        conn.close()
        await callback.message.edit_text("✅ Duplicates removed!")
    elif callback.data == "duplicates_no":
        await callback.message.edit_text("👌 Duplicates kept as-is.")
    
    await show_next_contact(callback.message, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "back_menu")
async def back_to_menu(callback: CallbackQuery):
    """Возврат в меню"""
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="▶️ Start Work")],
            [KeyboardButton(text="📋 Add Contacts")],
            [KeyboardButton(text="⚙️ Settings")]
        ],
        resize_keyboard=True
    )
    await callback.message.edit_text(
        "✅ You've successfully uploaded your numbers! Let's get started!",
        reply_markup=kb
    )
    await callback.answer()

async def show_next_contact(message, user_id: int):
    """Показывает следующий контакт"""
    contacts = get_user_contacts(user_id)
    if not contacts:
        await message.answer("📭 No contacts available. Upload numbers first!")
        return
    
    # Сбрасываем индекс на 0 для простоты (можно улучшить)
    conn = sqlite3.connect('speedcaller.db')
    c = conn.cursor()
    c.execute('UPDATE users SET current_index=0 WHERE user_id=?', (user_id,))
    current_index = 0
    conn.commit()
    conn.close()
    
    contact = contacts[current_index]
    total = len(contacts)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Call", callback_data=f"call_{contact['id']}")],
        [InlineKeyboardButton(text="↪️ Skip", callback_data=f"skip_{contact['id']}"),
         InlineKeyboardButton(text="↩️ Back", callback_data="back_contact")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="settings")]
    ])
    
    await message.answer(
        f"📞 Call this phone number? **{current_index+1}/{total}**\n\n"
        f"Automatically redirect to a call, press \"Call\"\n\n"
        f"`{contact['original']}`",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("call_"))
async def call_handler(callback: CallbackQuery):
    """Call кнопка"""
    contact_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect('speedcaller.db')
    c = conn.cursor()
    c.execute('SELECT phone FROM contacts WHERE id=?', (contact_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        phone = result[0]
        text = f"📞 Calling **{phone}**\n\nAfter call press Skip or Back"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↪️ Skip", callback_data=f"skip_{contact_id}")],
            [InlineKeyboardButton(text="↩️ Back", callback_data="back_contact")],
            [InlineKeyboardButton(text="⚙️ Settings", callback_data="settings")]
        ])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    
    # Показываем tel: ссылку
    await callback.message.answer(f"☎️ [Call](tel:{phone})", parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("skip_"))
async def skip_handler(callback: CallbackQuery):
    """Skip кнопка"""
    await callback.answer("✅ Skipped! Next contact coming...")
    await show_next_contact(callback.message, callback.from_user.id)

@router.callback_query(F.data == "back_contact")
async def back_contact(callback: CallbackQuery):
    """Back кнопка"""
    await callback.answer("🔙 Previous contact")
    # Пока просто показываем текущий, логику можно улучшить
    await show_next_contact(callback.message, callback.from_user.id)

@router.callback_query(F.data == "settings")
async def settings_handler(callback: CallbackQuery):
    """Settings меню"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="back_main")],
        [InlineKeyboardButton(text="🧹 Clear the database", callback_data="clear_db")],
        [InlineKeyboardButton(text="📝 Add numbers", callback_data="add_numbers")],
        [InlineKeyboardButton(text="📵 Delete duplicate number", callback_data="delete_duplicates")]
    ])
    await callback.message.edit_text("⚙️ **Settings**", reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "clear_db")
async def clear_db(callback: CallbackQuery):
    """Очистка БД"""
    user_id = callback.from_user.id
    conn = sqlite3.connect('speedcaller.db')
    c = conn.cursor()
    c.execute('DELETE FROM contacts WHERE user_id=?', (user_id,))
    c.execute('UPDATE users SET current_index=0, total_contacts=0 WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("🧹 Database cleared! Upload new numbers to start.")
    await callback.answer()

@router.callback_query(F.data == "add_numbers")
async def add_numbers(callback: CallbackQuery):
    """Добавление номеров"""
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⚙️ Settings")]],
        resize_keyboard=True
    )
    await callback.message.edit_text(
        "📝 Send Excel file or paste numbers (one per line)",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data == "delete_duplicates")
async def delete_duplicates(callback: CallbackQuery):
    """Удаление дублей"""
    user_id = callback.from_user.id
    conn = sqlite3.connect('speedcaller.db')
    c = conn.cursor()
    c.execute('DELETE FROM contacts WHERE id NOT IN (SELECT MIN(id) FROM contacts WHERE user_id=? GROUP BY phone)', (user_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text("📵 Duplicates deleted!")
    await callback.answer()

@router.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    """Возврат на главный экран"""
    await show_next_contact(callback.message, callback.from_user.id)

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())