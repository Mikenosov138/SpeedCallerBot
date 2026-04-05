import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import openpyxl
import sqlite3
import os
import re
import logging
import time
import threading

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Token from environment
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logger.error("BOT_TOKEN not found in environment variables. Set it in Render dashboard.")
    raise SystemExit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# Database connection
conn = sqlite3.connect("speedcaller.db", check_same_thread=False)
cursor = conn.cursor()

# Create table if not exists
cursor.execute("""
CREATE TABLE IF NOT EXISTS numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# User state management
user_states = {}
message_cache = {}

def normalize_phone(value):
    """Normalize phone number - adds + if missing, cleans format"""
    if value is None:
        return None
    s = str(value).strip()
    s = re.sub(r"[^\d+]", "", s)
    
    if not s or len(s) < 11 or len(s) > 14:
        return None
    
    # Add + if missing
    if not s.startswith('+'):
        s = '+' + s
    
    # Validate Russian/International format
    if len(s) < 12 or len(s) > 14:
        return None
    
    return s

def get_user_stats(user_id):
    """Get total unique numbers for user"""
    cursor.execute("SELECT COUNT(*) FROM numbers WHERE user_id=?", (user_id,))
    return cursor.fetchone()[0]

def get_user_numbers(user_id):
    """Get all numbers for user in order"""
    cursor.execute("SELECT phone FROM numbers WHERE user_id=? ORDER BY id ASC", (user_id,))
    return [row[0] for row in cursor.fetchall()]

def get_current_number(user_id):
    """Get current number based on user state"""
    state = user_states.get(user_id, {})
    numbers = get_user_numbers(user_id)
    current_index = state.get('current_index', 0)
    
    if current_index < len(numbers):
        return numbers[current_index], current_index
    else:
        state['current_index'] = 0
        return numbers[0], 0 if numbers else (None, 0)

def update_user_index(user_id, direction):
    """Update current index: 1=next, -1=previous"""
    state = user_states.get(user_id, {'current_index': 0})
    numbers = get_user_numbers(user_id)
    
    if not numbers:
        return
    
    current_index = state['current_index']
    current_index += direction
    
    # Wrap around
    if current_index >= len(numbers):
        current_index = 0
    elif current_index < 0:
        current_index = len(numbers) - 1
    
    state['current_index'] = current_index
    user_states[user_id] = state

def clear_user_numbers(user_id):
    """Clear all numbers for user"""
    cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
    conn.commit()
    user_states[user_id] = {'current_index': 0}

def add_number(user_id, phone):
    """Add normalized phone if unique"""
    normalized = normalize_phone(phone)
    if normalized:
        cursor.execute("INSERT OR IGNORE INTO numbers (user_id, phone) VALUES (?, ?)", (user_id, normalized))
        conn.commit()
        return True
    return False

def import_from_excel(user_id, file_bytes):
    """Import from Excel file"""
       temp_name = f"temp_{int(time.time())}_{user_id}.xlsx"
    with open(temp_name, "wb") as f:
        f.write(file_bytes)
    
    added = 0
    try:
        wb = openpyxl.load_workbook(temp_name, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if add_number(user_id, cell):
                        added += 1
        conn.commit()
    except Exception as e:
        logger.error(f"Excel import error: {e}")
    finally:
        try:
            os.remove(temp_name)
        except:
            pass
    
    return added

def import_from_text(user_id, text):
    """Import from text message"""
    added
