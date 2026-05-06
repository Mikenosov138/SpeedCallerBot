import os
import time
import sqlite3
import openpyxl
from telebot import TeleBot, types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException

TOKEN = "PASTE_YOUR_TOKEN_HERE"
bot = TeleBot(TOKEN, parse_mode="HTML")

user_state = {}

# База UNIQUE номеров
def init_db():
    conn = sqlite3.connect("speedcaller_v6.db", check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        phone TEXT UNIQUE,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

    cursor.execute("UPDATE numbers SET status='pending' WHERE status='new'")
    conn.commit()

    return conn, cursor

conn, cursor = init_db()

def normalize_phone(phone):
    if phone is None:
        return None
    s = str(phone).strip()
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit() or ch == "+")
    digits = digits.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if digits.startswith("8") and len(digits) == 11:
        digits = "+7" + digits[1:]
    elif digits.startswith("7") and len(digits) == 11:
        digits = "+" + digits
    elif digits.startswith("+") and len(digits) >= 10:
        pass
    elif digits.isdigit() and len(digits) >= 10:
        digits = "+" + digits
    return digits

def get_user_numbers(user_id):
    cursor.execute(
        "SELECT id, phone FROM numbers WHERE user_id=? AND status='pending' ORDER BY id",
        (user_id,)
    )
    return cursor.fetchall()

def get_number_by_id(num_id):
    cursor.execute("SELECT id, phone, user_id, status FROM numbers WHERE id=?", (num_id,))
    return cursor.fetchone()

def count_pending(user_id):
    cursor.execute(
        "SELECT COUNT(*) FROM numbers WHERE user_id=? AND status='pending'",
        (user_id,)
    )
    row = cursor.fetchone()
    return row[0] if row else 0

def import_numbers(user_id, data, source="text"):
    count_added = 0
    numbers = []

    if source == "excel":
        try:
            wb = openpyxl.load_workbook(data)
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        if cell is not None and str(cell).strip():
                            numbers.append(str(cell).strip())
        except:
            return 0
    else:
        numbers = [line.strip() for line in data.splitlines() if line.strip()]

    numbers = [normalize_phone(n) for n in numbers]
    numbers = [n for n in numbers if n]
    numbers = list(dict.fromkeys(numbers))

    for phone in numbers:
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO numbers (user_id, phone, status) VALUES (?, ?, 'pending')",
                (user_id, phone)
            )
            if cursor.rowcount > 0:
                count_added += 1
        except:
            pass

    conn.commit()
    return count_added

def clear_user_numbers(user_id):
    cursor.execute("DELETE FROM numbers WHERE user_id=?", (user_id,))
    conn.commit()

def remove_user_duplicates(user_id):
    cursor.execute("""
        DELETE FROM numbers
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM numbers
            WHERE user_id=?
            GROUP BY phone
        ) AND user_id=?
    """, (user_id, user_id))
    conn.commit()

def mark_number_called(num_id):
    cursor.execute("UPDATE numbers SET status='called' WHERE id=?", (num_id,))
    conn.commit()

def mark_number_skipped(num_id):
    cursor.execute("UPDATE numbers SET status='skipped' WHERE id=?", (num_id,))
    conn.commit()

def clean_phone(phone):
    s = str(phone).strip()
    digits = "".join(ch for ch in s if ch.isdigit() or ch == "+")
    digits = digits.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if digits.startswith("8") and len(digits) == 11:
        return "+7" + digits[1:]
    if digits.startswith("7") and len(digits) == 11 and not digits.startswith("+"):
        return "+" + digits
    if digits.startswith("+"):
        return digits
    if digits.isdigit():
        return "+" + digits
    return digits

@bot.callback_query_handler(func=lambda call: call.data == "remove_duplicates")
def remove_duplicates(call):
    user_id = call.from_user.id
    remove_user_duplicates(user_id)
    bot.answer_callback_query(call.id, "🧹 Duplicates removed!")
    bot.answer_callback_query(call.id, "🧹 Duplicates removed!")

@bot.callback_query_handler(func=lambda call: call.data == "load_menu")
def load_menu(call):
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("📊 Excel", callback_data="load_excel"))
    kb.row(InlineKeyboardButton("📝 Text", callback_data="load_text"))
    kb.row(InlineKeyboardButton("↩️ Return to call", callback_data="start_calling"))
    kb.row(InlineKeyboardButton("🗑️ Clear ALL", callback_data="clear_all"))
    kb.row(InlineKeyboardButton("🧹 Remove duplicates", callback_data="remove_duplicates"))
    kb.row(InlineKeyboardButton("↩️ Main Menu", callback_data="back_main"))

    bot.edit_message_text(
        "📥 Load numbers:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda call: call.data == "load_excel")
def load_excel(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📎 Send Excel file (.xlsx)")

@bot.callback_query_handler(func=lambda call: call.data == "load_text")
def load_text(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📝 Send numbers as text, one per line")

@bot.callback_query_handler(func=lambda call: call.data == "clear_all")
def clear_all(call):
    user_id = call.from_user.id
    clear_user_numbers(user_id)
    bot.answer_callback_query(call.id, "🗑️ Cleared!")
    bot.send_message(call.message.chat.id, "🗑️ All your numbers were deleted.")

@bot.callback_query_handler(func=lambda call: call.data == "back_main")
def back_main(call):
    bot.answer_callback_query(call.id)
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("▶️ START", callback_data="start_calling"))
    kb.row(InlineKeyboardButton("📥 Load numbers", callback_data="load_menu"))
    bot.edit_message_text(
        "Menu",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=kb
    )

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    file_info = bot.get_file(message.document.file_id)
    downloaded = bot.download_file(file_info.file_path)

    filename = message.document.file_name.lower()
    if not filename.endswith(".xlsx"):
        bot.send_message(message.chat.id, "❌ Only .xlsx files are supported.")
        return

    tmp_path = f"tmp_{message.document.file_unique_id}.xlsx"
    with open(tmp_path, "wb") as f:
        f.write(downloaded)

    added = import_numbers(user_id, tmp_path, source="excel")
    try:
        os.remove(tmp_path)
    except:
        pass

    total = count_pending(user_id)
    bot.send_message(message.chat.id, f"✅ {added} numbers imported. Total pending: {total}")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text in ["/start", "START", "start"]:
        return

    if "\n" in text or text.startswith("+") or text[:1].isdigit():
        added = import_numbers(user_id, text, source="text")
        total = count_pending(user_id)
        bot.send_message(message.chat.id, f"✅ {added} numbers imported. Total pending: {total}")
        @bot.callback_query_handler(func=lambda call: call.data == "start_calling")
def start_calling(call):
    bot.answer_callback_query(call.id)

    user_id = call.from_user.id
    numbers = get_user_numbers(user_id)

    if not numbers:
        bot.send_message(call.message.chat.id, "📭 No numbers loaded.")
        return

    if user_id not in user_state:
        user_state[user_id] = {"index": 0}

    user_state[user_id]["index"] = 0

    num_id, phone = numbers[0]
    phone_e164 = clean_phone(phone)

    bot.send_message(call.message.chat.id, f"📞 {phone_e164}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("call_"))
def handle_call(call):
    bot.answer_callback_query(call.id)

    try:
        num_id = int(call.data.split("_", 1)[1])
    except:
        bot.send_message(call.message.chat.id, "❌ Invalid number id.")
        return

    row = get_number_by_id(num_id)
    if not row:
        bot.send_message(call.message.chat.id, "❌ Number not found.")
        return

    _, phone, user_id, status = row
    phone_e164 = clean_phone(phone)

    mark_number_called(num_id)

    bot.send_message(call.message.chat.id, f"📞 {phone_e164}")

    if user_id not in user_state:
        user_state[user_id] = {"index": 0}

    user_state[user_id]["index"] += 1


@bot.callback_query_handler(func=lambda call: call.data.startswith("skip_"))
def handle_skip(call):
    bot.answer_callback_query(call.id)

    try:
        num_id = int(call.data.split("_", 1)[1])
    except:
        bot.send_message(call.message.chat.id, "❌ Invalid number id.")
        return

    row = get_number_by_id(num_id)
    if not row:
        bot.send_message(call.message.chat.id, "❌ Number not found.")
        return

    _, phone, user_id, status = row
    mark_number_skipped(num_id)

    numbers = get_user_numbers(user_id)
    if not numbers:
        bot.send_message(call.message.chat.id, "📭 No numbers loaded.")
        return

    current_index = user_state.get(user_id, {}).get("index", 0)
    if current_index >= len(numbers):
        current_index = len(numbers) - 1

    next_index = current_index + 1
    if next_index >= len(numbers):
        bot.send_message(call.message.chat.id, "✅ End of list.")
        return

    user_state.setdefault(user_id, {})["index"] = next_index
    next_num_id, next_phone = numbers[next_index]
    bot.send_message(call.message.chat.id, f"📞 {clean_phone(next_phone)}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("back_"))
def handle_back(call):
    bot.answer_callback_query(call.id)

    try:
        num_id = int(call.data.split("_", 1)[1])
    except:
        bot.send_message(call.message.chat.id, "❌ Invalid number id.")
        return

    row = get_number_by_id(num_id)
    if not row:
        bot.send_message(call.message.chat.id, "❌ Number not found.")
        return

    _, phone, user_id, status = row

    numbers = get_user_numbers(user_id)
    if not numbers:
        bot.send_message(call.message.chat.id, "📭 No numbers loaded.")
        return

    current_index = user_state.get(user_id, {}).get("index", 0)
    prev_index = current_index - 1
    if prev_index < 0:
        bot.send_message(call.message.chat.id, "⏮️ Already first number.")
        return

    user_state.setdefault(user_id, {})["index"] = prev_index
    prev_num_id, prev_phone = numbers[prev_index]
    bot.send_message(call.message.chat.id, f"📞 {clean_phone(prev_phone)}")


if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)

def build_number_markup(num_id):
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("📞 CALL", callback_data=f"call_{num_id}"),
        InlineKeyboardButton("⏭ SKIP", callback_data=f"skip_{num_id}"),
        InlineKeyboardButton("⬅ BACK", callback_data=f"back_{num_id}")
    )
    return kb


@bot.callback_query_handler(func=lambda call: call.data == "start_calling")
def start_calling(call):
    bot.answer_callback_query(call.id)

    user_id = call.from_user.id
    numbers = get_user_numbers(user_id)

    if not numbers:
        bot.send_message(call.message.chat.id, "📭 No numbers loaded.")
        return

    user_state[user_id] = {"index": 0}

    num_id, phone = numbers[0]
    phone_e164 = clean_phone(phone)

    bot.send_message(
        call.message.chat.id,
        f"📞 {phone_e164}",
        reply_markup=build_number_markup(num_id)
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("call_"))
def handle_call(call):
    bot.answer_callback_query(call.id)

    try:
        num_id = int(call.data.split("_", 1)[1])
    except:
        bot.send_message(call.message.chat.id, "❌ Invalid number id.")
        return

    row = get_number_by_id(num_id)
    if not row:
        bot.send_message(call.message.chat.id, "❌ Number not found.")
        return

    _, phone, user_id, status = row
    phone_e164 = clean_phone(phone)

    mark_number_called(num_id)

    bot.send_message(
        call.message.chat.id,
        f"📞 {phone_e164}",
        reply_markup=build_number_markup(num_id)
    )

    user_state.setdefault(user_id, {})
    user_state[user_id]["index"] = user_state[user_id].get("index", 0) + 1


@bot.callback_query_handler(func=lambda call: call.data.startswith("skip_"))
def handle_skip(call):
    bot.answer_callback_query(call.id)

    try:
        num_id = int(call.data.split("_", 1)[1])
    except:
        bot.send_message(call.message.chat.id, "❌ Invalid number id.")
        return

    row = get_number_by_id(num_id)
    if not row:
        bot.send_message(call.message.chat.id, "❌ Number not found.")
        return

    _, phone, user_id, status = row
    mark_number_skipped(num_id)

    numbers = get_user_numbers(user_id)
    if not numbers:
        bot.send_message(call.message.chat.id, "📭 No numbers loaded.")
        return

    current_index = 0
    for i, (nid, ph) in enumerate(numbers):
        if nid == num_id:
            current_index = i
            break

    next_index = current_index + 1
    if next_index >= len(numbers):
        bot.send_message(call.message.chat.id, "✅ End of list.")
        return

    next_num_id, next_phone = numbers[next_index]
    user_state.setdefault(user_id, {})
    user_state[user_id]["index"] = next_index

    bot.send_message(
        call.message.chat.id,
        f"📞 {clean_phone(next_phone)}",
        reply_markup=build_number_markup(next_num_id)
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("back_"))
def handle_back(call):
    bot.answer_callback_query(call.id)

    try:
        num_id = int(call.data.split("_", 1)[1])
    except:
        bot.send_message(call.message.chat.id, "❌ Invalid number id.")
        return

    row = get_number_by_id(num_id)
    if not row:
        bot.send_message(call.message.chat.id, "❌ Number not found.")
        return

    _, phone, user_id, status = row

    numbers = get_user_numbers(user_id)
    if not numbers:
        bot.send_message(call.message.chat.id, "📭 No numbers loaded.")
        return

    current_index = 0
    for i, (nid, ph) in enumerate(numbers):
        if nid == num_id:
            current_index = i
            break

    prev_index = current_index - 1
    if prev_index < 0:
        bot.send_message(call.message.chat.id, "⏮️ Already first number.")
        return

    prev_num_id, prev_phone = numbers[prev_index]
    user_state.setdefault(user_id, {})
    user_state[user_id]["index"] = prev_index

    bot.send_message(
        call.message.chat.id,
        f"📞 {clean_phone(prev_phone)}",
        reply_markup=build_number_markup(prev_num_id)
    )
if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)

    bot.infinity_polling(
        skip_pending=True,
        timeout=20,
        long_polling_timeout=20
    )
