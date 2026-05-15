import logging
import sqlite3
import datetime
from datetime import timedelta, date
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
import random
import os
from threading import Thread

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8790602142:AAF0gqNc7xYkeOxccIqTm16Sg9ObygClRec")
ADMIN_ID = 8739215730
PORT = int(os.environ.get("PORT", 5000))

# Flask App Setup (To keep Render dyno alive)
app = Flask(__name__)

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- DATABASE SETUP ---
DB_NAME = "leaderboard.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        total_xp INTEGER DEFAULT 0,
        total_msgs INTEGER DEFAULT 0,
        last_msg_time TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS message_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        group_id INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS spam_block (
        user_id INTEGER PRIMARY KEY,
        unblock_time TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

# --- HELPER FUNCTIONS ---

def get_rank_name(xp):
    if xp < 100: return "Bronze 🥉"
    if xp < 500: return "Silver 🥈"
    if xp < 1000: return "Gold 🥇"
    if xp < 2500: return "Platinum 💎"
    if xp < 5000: return "Diamond 💠"
    if xp < 10000: return "Master 🏆"
    return "Legend 👑"

def is_user_spamming(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT unblock_time FROM spam_block WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        unblock_time = datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        if datetime.datetime.now() < unblock_time:
            return True
        else:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("DELETE FROM spam_block WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            return False
    return False

def check_spam_trigger(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    one_min_ago = datetime.datetime.now() - timedelta(minutes=1)
    
    c.execute("SELECT COUNT(*) FROM message_log WHERE user_id = ? AND timestamp > ?", 
              (user_id, one_min_ago.strftime('%Y-%m-%d %H:%M:%S')))
    count = c.fetchone()[0]
    
    if count >= 15:
        unblock_time = datetime.datetime.now() + timedelta(minutes=10)
        c.execute("INSERT OR REPLACE INTO spam_block (user_id, unblock_time) VALUES (?, ?)", 
                  (user_id, unblock_time.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def update_user_data(user_id, username, first_name, group_id):
    if is_user_spamming(user_id):
        return False 
    if check_spam_trigger(user_id):
        return False 

    xp_gain = random.randint(5, 15)
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('''INSERT INTO users (user_id, username, first_name, total_xp, total_msgs, last_msg_time)
                 VALUES (?, ?, ?, ?, ?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET
                 username = excluded.username,
                 first_name = excluded.first_name,
                 total_xp = total_xp + ?,
                 total_msgs = total_msgs + 1,
                 last_msg_time = CURRENT_TIMESTAMP''',
              (user_id, username, first_name, 0, 0, datetime.datetime.now(), xp_gain))
    
    c.execute("INSERT INTO message_log (user_id, group_id, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)",
              (user_id, group_id))
              
    conn.commit()
    conn.close()
    return True

# --- HANDLERS ---

def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id < 0: return 
    
    welcome_text = (
        "👋 <b>Welcome to the Leaderboard Bot!</b>\n\n"
        "I track messages and XP in groups.\n\n"
        "Commands:\n"
        "/myprofile - View your stats\n"
        "/rank - Show your rank card\n"
        "Add me to a group to start tracking!"
    )
    update.message.reply_text(welcome_text, parse_mode='HTML')

def track_message(update: Update, context: CallbackContext):
    if update.effective_chat.type == 'private': return 
    
    user = update.effective_user
    if not user: return
    
    group_id = update.effective_chat.id
    
    success = update_user_data(user.id, user.username, user.first_name, group_id)
    
    if not success:
        pass

def my_profile(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("SELECT total_msgs, total_xp FROM users WHERE user_id = ?", (user_id,))
    user_data = c.fetchone()
    
    if not user_data:
        update.message.reply_text("You haven't sent any messages in groups yet!")
        conn.close()
        return
    
    total_msgs, total_xp = user_data
    
    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    c.execute("SELECT COUNT(*) FROM message_log WHERE user_id = ? AND timestamp >= ?", 
              (user_id, today_start.strftime('%Y-%m-%d %H:%M:%S')))
    today_msgs = c.fetchone()[0]
    
    week_start = datetime.datetime.now() - timedelta(days=datetime.datetime.now().weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    c.execute("SELECT COUNT(*) FROM message_log WHERE user_id = ? AND timestamp >= ?", 
              (user_id, week_start.strftime('%Y-%m-%d %H:%M:%S')))
    week_msgs = c.fetchone()[0]
    
    conn.close()
    
    rank_name = get_rank_name(total_xp)
    
    text = (
        f"👤 <b>Profile</b>: {update.effective_user.first_name}\n"
        f"🏅 <b>Rank</b>: {rank_name}\n\n"
        f"📊 <b>Statistics</b>:\n"
        f"   • Total Messages: {total_msgs}\n"
        f"   • Total XP: {total_xp}\n"
        f"   • Today's Messages: {today_msgs}\n"
        f"   • Weekly Messages: {week_msgs}"
    )
    update.message.reply_text(text, parse_mode='HTML')

def show_rank(update: Update, context: CallbackContext):
    user user_id = update.effective_user.id
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("SELECT total_xp FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    
    if not row:
        update.message.reply_text("No data found. Send some messages in a group first!")
        return
        
    user_xp = row[0]
    rank_name = get_rank_name(user_xp)
    
    c.execute("SELECT user_id FROM users ORDER BY total_xp DESC")
    all_users = c.fetchall()
    user_rank = 1
    found = False
    for u in all_users:
        if u[0] == user_id:
            found = True
            break
        user_rank += 1
        
    conn.close()
    
    name = update.effective_user.first_name
    
    text = (
        f"🎖️ <b>{name}</b>'s Rank Card\n\n"
        f"🏆 Rank: #{user_rank}\n"
        f"🎖️ Title: {rank_name}\n"
        f"✨ XP: {user_xp}"
    )
    update.message.reply_text(text, parse_mode='HTML')

def get_leaderboard_data(period, group_id=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    query = ""
    params = ()
    
    wrapper = '' if group_id is None else '''FROM users u JOIN message_log m ON u.user_id = m.user_id 
                                             WHERE m.group_id = ? '''

    if period == "today":
        start_time = datetime.datetime.now().replace(hour=0, minute=0, port=0, microsecond=0) # Typo fix port->second
        query = f'''SELECT u.user_id, u.first_name, COUNT(m.id) as msg_count 
                    {wrapper}
                    AND m.timestamp >= ? '''
        params = (group_id, start_time.strftime('%Y-%m-%d %H:%M:%S')) if group_id else (start_time.strftime('%Y-%m-%d %H:%M:%S'),)
            
    elif period == "week":
        start_time = datetime.datetime.now() - timedelta(days=datetime.datetime.now().weekday())
        start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        query = f'''SELECT u.user_id, u.first_name, COUNT(m.id) as msg_count 
                    {wrapper}
                    AND m.timestamp >= ? '''
        params = (group_id, start_time.strftime('%Y-%m-%d %H:%M:%S')) if group_id else (start_time.strftime('%Y-%m-%d %H:%M:%S'),)

    else: # Overall
        query = "SELECT user_id, first_name, total_msgs FROM users"
        if group_id:
            query = '''SELECT u.user_id, u.first_name, COUNT(m.id) as msg_count 
                       FROM users u JOIN message_log m ON u.user_id = m.user_id
                       WHERE m.group_id = ? GROUP BY u.user_id'''
            params = (group_id,)

    if period in ["today", "week"]:
         query += " GROUP BY u.user_id "
    
    query += " ORDER BY msg_count DESC LIMIT 10"
    
    c.execute(query, params)
    data = c.fetchall()
    conn.close()
    return data

def chatranking(update: Update, context: CallbackContext):
    period = "overall"
    group_id = update.effective_chat.id
    
    data = get_leaderboard_data(period, group_id)
    
    keyboard = [
        [InlineKeyboardButton("📅 Today", callback_data=f'lb_today_{group_id}'),
         InlineKeyboardButton("📆 Week", callback_data=f'lb_week_{group_id}')],
        [InlineKeyboardButton("🌍 Overall", callback_data=f'lb_overall_{group_id}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text_header = "<b>🏆 Leaderboard (Overall)</b>\n\n"
    leaderboard_text = format_leaderboard_text(data)
    
    update.message.reply_text(text_header + leaderboard_text, reply_markup=reply_markup, parse_mode='HTML')

def format_leaderboard_text(data):
    if not data:
        return "No messages yet!"
    
    text = ""
    medals = ["🥇", "🥈", "🥉"]
    
    for idx, (user_id, name, count) in enumerate(data):
        rank = idx + 1
        medal = medals[idx] if rank <= 3 else f"{rank}."
        text += f"{medal} <b>{name}</b>: {count} msgs\n"
        
    def leaderboard_button_callback(update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        
        data_parts = query.data.split('_')
        period = data_parts[1]
        group_id = int(data_parts[2])
        
        lb_data = get_leaderboard_data(period, group_id)
        
        keyboard = [
            [InlineKeyboardButton("📅 Today", callback_data=f'lb_today_{group_id}'),
             InlineKeyboardButton("📆 Week", callback_data=f'lb_week_{group_id}')],
            [InlineKeyboardButton("🌍 Overall", callback_data=f'lb_overall_{group_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        title = "Today" if period == "today" else ("This Week" if period == "week" else "Overall")
        text_header = f"<b>🏆 Leaderboard ({title})</b>\n\n"
        leaderboard_text = format_leaderboard_text(lb_data)
        
        query.edit_message_text(text=text_header + leaderboard_text, reply_markup=reply_markup, parse_mode='HTML')
        
# --- FLASK ROUTE (Keep Alive) ---
@app.route('/')
def index():
    return "Bot is running and alive!"

# --- BOT THREAD FUNCTION ---
def run_bot():
    init_db()
    
    # Create Updater and Dispatcher
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Register Handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("myprofile", my_profile))
    dp.add_handler(CommandHandler("rank", show_rank))
    dp.add_handler(CommandHandler("chatranking", chatranking))
    dp.add_handler(CallbackQueryHandler(leaderboard_button_callback, pattern='^lb_'))
    dp.add_handler(MessageHandler(Filters.all & ~Filters.command, track_message))
    
    # Start Polling
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    # Run Flask in the main thread (to satisfy Render port binding)
    # Run Bot in a separate thread
    bot_thread = Thread(target=run_bot)
    bot_thread.start()
    
    app.run(host="0.0.0.0", port=PORT)
