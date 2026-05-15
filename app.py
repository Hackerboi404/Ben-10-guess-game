import logging
import sqlite3
import datetime
from datetime import timedelta, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
import random

# --- CONFIGURATION ---
BOT_TOKEN = "8790602142:AAF0gqNc7xYkeOxccIqTm16Sg9ObygClRec"  # Replace with your actual Bot Token
ADMIN_ID = 8739215730  # Replace with your Telegram User ID to receive errors/logs

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
    
    # Users Table: Stores user info and XP
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        total_xp INTEGER DEFAULT 0,
        total_msgs INTEGER DEFAULT 0,
        last_msg_time TIMESTAMP
    )''')
    
    # Message Logs: To calculate daily/weekly stats
    c.execute('''CREATE TABLE IF NOT EXISTS message_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        group_id INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Spam Control: Store blocked users and their unblock time
    c.execute('''CREATE TABLE IF NOT EXISTS spam_block (
        user_id INTEGER PRIMARY KEY,
        unblock_time TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

# --- HELPER FUNCTIONS ---

def get_rank_name(xp):
    """Determines Rank based on XP."""
    if xp < 100: return "Bronze 🥉"
    if xp < 500: return "Silver 🥈"
    if xp < 1000: return "Gold 🥇"
    if xp < 2500: return "Platinum 💎"
    if xp < 5000: return "Diamond 💠"
    if xp < 10000: return "Master 🏆"
    return "Legend 👑"

def is_user_spamming(user_id):
    """Checks if a user is currently blocked for spamming."""
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
            # Unblock if time has passed
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("DELETE FROM spam_block WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            return False
    return False

def check_spam_trigger(user_id):
    """
    Simple anti-spam logic: If a user sends more than 15 messages in 1 minute,
    block them for 10 minutes.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    one_min_ago = datetime.datetime.now() - timedelta(minutes=1)
    
    # Count messages in last minute
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
    """Updates XP, message count, and logs the message."""
    if is_user_spamming(user_id):
        return False # User is blocked

    # Check for spam trigger
    if check_spam_trigger(user_id):
        return False # User just got blocked

    xp_gain = random.randint(5, 15) # Random XP per message
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Update main user stats
    c.execute('''INSERT INTO users (user_id, username, first_name, total_xp, total_msgs, last_msg_time)
                 VALUES (?, ?, ?, ?, ?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET
                 username = excluded.username,
                 first_name = excluded.first_name,
                 total_xp = total_xp + ?,
                 total_msgs = total_msgs + 1,
                 last_msg_time = CURRENT_TIMESTAMP''',
              (user_id, username, first_name, 0, 0, datetime.datetime.now(), xp_gain))
    
    # Log message for daily/weekly stats
    c.execute("INSERT INTO message_log (user_id, group_id, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)",
              (user_id, group_id))
              
    conn.commit()
    conn.close()
    return True

# --- HANDLERS ---

def start(update: Update, context: CallbackContext):
    """Handles /start command in DM."""
    chat_id = update.effective_chat.id
    if chat_id < 0: return # Ignore groups
    
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
    """Tracks every message sent in a group."""
    if update.effective_chat.type == 'private': return # Ignore DMs
    
    user = update.effective_user
    if not user: return
    
    group_id = update.effective_chat.id
    
    success = update_user_data(user.id, user.username, user.first_name, group_id)
    
    if not success:
        # Optional: Send a hint that they are blocked (or just ignore silently)
        pass

def my_profile(update: Update, context: CallbackContext):
    """Shows /myprofile."""
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Get Overall Stats
    c.execute("SELECT total_msgs, total_xp FROM users WHERE user_id = ?", (user_id,))
    user_data = c.fetchone()
    
    if not user_data:
        update.message.reply_text("You haven't sent any messages in groups yet!")
        conn.close()
        return
    
    total_msgs, total_xp = user_data
    
    # Calculate Today's Stats
    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    c.execute("SELECT COUNT(*) FROM message_log WHERE user_id = ? AND timestamp >= ?", 
              (user_id, today_start.strftime('%Y-%m-%d %H:%M:%S')))
    today_msgs = c.fetchone()[0]
    
    # Calculate Week's Stats
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
    """Shows /rank card for the user."""
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Get User XP
    c.execute("SELECT total_xp FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    
    if not row:
        update.message.reply_text("No data found. Send some messages in a group first!")
        return
        
    user_xp = row[0]
    rank_name = get_rank_name(user_xp)
    
    # Calculate Global Rank
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
    """Helper to fetch leaderboard data based on period."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    query = ""
    params = ()
    
    if period == "today":
        start_time = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        query = '''SELECT u.user_id, u.first_name, COUNT(m.id) as msg_count 
                   FROM users u JOIN message_log m ON u.user_id = m.user_id
                   WHERE m.timestamp >= ? '''
        params = (start_time.strftime('%Y-%m-%d %H:%M:%S'),)
        if group_id:
            query += " AND m.group_id = ? "
            params = (params[0], group_id)
            
    elif period == "week":
        start_time = datetime.datetime.now() - timedelta(days=datetime.datetime.now().weekday())
        start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        query = '''SELECT u.user_id, u.first_name, COUNT(m.id) as msg_count 
                   FROM users u JOIN message_log m ON u.user_id = m.user_id
                   WHERE m.timestamp >= ? '''
        params = (start_time.strftime('%Y-%m-%d %H:%M:%S'),)
        if group_id:
            query += " AND m.group_id = ? "
            params = (params[0], group_id)

    else: # Overall
        query = "SELECT user_id, first_name, total_msgs FROM users"
        if group_id:
            query = '''SELECT u.user_id, u.first_name, COUNT(m.id) as msg_count 
                       FROM users u JOIN message_log m ON u.user_id = m.user_id
                       WHERE m.group_id = ? GROUP BY u.user_id'''
            params = (group_id,)

    if period != "overall" or group_id:
        if period in ["today", "week"]:
             query += " GROUP BY u.user_id "
    
    query += " ORDER BY msg_count DESC LIMIT 10"
    
    c.execute(query, params)
    data = c.fetchall()
    conn.close()
    return data

def chatranking(update: Update, context: CallbackContext):
    """Handles /chatranking command."""
    # Default view: Overall
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
        
    return text

def leaderboard_button_callback(update: Update, context: CallbackContext):
    """Handles button clicks on the leaderboard."""
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

def main():
    init_db()
    
    # Create Updater
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Command Handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("myprofile", my_profile))
    dp.add_handler(CommandHandler("rank", show_rank))
    dp.add_handler(CommandHandler("chatranking", chatranking))
    
    # Button Callback Handler
    dp.add_handler(CallbackQueryHandler(leaderboard_button_callback, pattern='^lb_'))
    
    # Message Handler (tracks text, stickers, photos, etc.)
    dp.add_handler(MessageHandler(Filters.all & ~Filters.command, track_message))
    
    # Start Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
