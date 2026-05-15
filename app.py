import logging
import sqlite3
import datetime
from datetime import timedelta
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

# Flask App Setup
app = Flask(__name__)

# Logging Setup
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

def check_and_reset_daily_logs():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    c.execute("SELECT COUNT(*) FROM message_log WHERE timestamp < ?", (today_start.strftime('%Y-%m-%d %H:%M:%S'),))
    if c.fetchone()[0] > 0:
        logger.info("Performing daily reset...")
        c.execute("DELETE FROM message_log WHERE timestamp < ?", (today_start.strftime('%Y-%m-%d %H:%M:%S'),))
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
        if datetime.datetime.now() < datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S'):
            return True
        else:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("DELETE FROM spam_block WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
    return False

def check_spam_trigger(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    one_min_ago = datetime.datetime.now() - timedelta(minutes=1)
    c.execute("SELECT COUNT(*) FROM message_log WHERE user_id = ? AND timestamp > ?", 
              (user_id, one_min_ago.strftime('%Y-%m-%d %H:%M:%S')))
    if c.fetchone()[0] >= 15:
        unblock_time = datetime.datetime.now() + timedelta(minutes=10)
        c.execute("INSERT OR REPLACE INTO spam_block (user_id, unblock_time) VALUES (?, ?)", 
                  (user_id, unblock_time.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def update_user_data(user_id, username, first_name, group_id, context):
    check_and_reset_daily_logs()
    if is_user_spamming(user_id) or check_spam_trigger(user_id):
        return False 

    xp_gain = random.randint(5, 15)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("SELECT total_msgs FROM users WHERE user_id = ?", (user_id,))
    prev_msgs = c.fetchone()[0] if c.fetchone() else 0
    
    c.execute('''INSERT INTO users (user_id, username, first_name, total_xp, total_msgs, last_msg_time)
                 VALUES (?, ?, ?, ?, ?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET
                 username = excluded.username,
                 first_name = excluded.first_name,
                 total_xp = total_xp + ?,
                 total_msgs = total_msgs + 1,
                 last_msg_time = CURRENT_TIMESTAMP''',
              (user_id, username, first_name, 0, 0, datetime.datetime.now(), xp_gain))
    
    c.execute("INSERT INTO message_log (user_id, group_id, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)", (user_id, group_id))
    conn.commit()
    
    c.execute("SELECT total_msgs FROM users WHERE user_id = ?", (user_id,))
    new_msgs = c.fetchone()[0]
    conn.close()
    
    if new_msgs in [2000, 5000, 10000]:
        try:
            context.bot.send_message(chat_id=group_id, text=f"🎉 <b>Congratulations {first_name}!</b>\n\nYou've completed <b>{new_msgs:,}</b> messages! 🚀", parse_mode='HTML')
        except:
            pass
    return True

# --- HANDLERS ---

def start(update: Update, context: CallbackContext):
    # Only work in Private Chat (DM)
    if update.effective_chat.type != 'private':
        return

    # Inline Keyboard Button
    keyboard = [[InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = """╔════════════════════╗
      ⚡ 𝐑𝐀𝐍𝐊𝐈𝐅𝐘 𝐁𝐎𝐓 ⚡
╚════════════════════╝

🏆 Advanced Group Ranking & XP System

✨ Track Messages
⚡ Earn XP
🎖️ Unlock Ranks
📊 Compete on Leaderboards

━━━━━━━━━━━━━━━━━━━

🔥 Features:
➤ Real-Time Chat Ranking
➤ Daily • Weekly • Overall Stats
➤ XP & Level System
➤ Smart Anti-Spam Protection
➤ Personal Profile & Rank Cards

━━━━━━━━━━━━━━━━━━━

📌 Commands:
/myprofile — View your profile stats
/rank — Check your XP & rank
/chatranking — Open leaderboard

💎 Add me to your group and start the competition!"""

    update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

def track_message(update: Update, context: CallbackContext):
    if update.effective_chat.type == 'private': return 
    user = update.effective_user
    if not user: return
    update_user_data(user.id, user.username, user.first_name, update.effective_chat.id, context)

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
    
    # Daily Stats
    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    c.execute("SELECT COUNT(*) FROM message_log WHERE user_id = ? AND timestamp >= ?", 
              (user_id, today_start.strftime('%Y-%m-%d %H:%M:%S')))
    today_msgs = c.fetchone()[0]
    
    # Weekly Stats
    week_start = datetime.datetime.now() - timedelta(days=datetime.datetime.now().weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    c.execute("SELECT COUNT(*) FROM message_log WHERE user_id = ? AND timestamp >= ?", 
              (user_id, week_start.strftime('%Y-%m-%d %H:%M:%S')))
    week_msgs = c.fetchone()[0]
    
    conn.close()
    rank_name = get_rank_name(total_xp)
    
    text = f"👤 <b>Profile</b>: {update.effective_user.first_name}\n🏅 <b>Rank</b>: {rank_name}\n\n📊 <b>Statistics</b>:\n   • Total Messages: {total_msgs:,}\n   • Total XP: {total_xp:,}\n   • Today: {today_msgs}\n   • Weekly: {week_msgs}"
    update.message.reply_text(text, parse_mode='HTML')

def show_rank(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT total_xp FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        update.message.reply_text("No data found.")
        return
    user_xp = row[0]
    rank_name = get_rank_name(user_xp)
    
    c.execute("SELECT user_id FROM users ORDER BY total_xp DESC")
    user_rank = 1
    for u in c.fetchall():
        if u[0] == user_id: break
        user_rank += 1
    conn.close()
    
    text = f"🎖️ <b>{update.effective_user.first_name}</b>'s Rank Card\n\n🏆 Rank: #{user_rank}\n🎖️ Title: {rank_name}\n✨ XP: {user_xp:,}"
    update.message.reply_text(text, parse_mode='HTML')

def get_leaderboard_data(period, group_id=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    query, params = "", ()
    
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

    if period in ["today", "week"]: query += " GROUP BY u.user_id "
    query += " ORDER BY msg_count DESC LIMIT 10"
    
    c.execute(query, params)
    data = c.fetchall()
    conn.close()
    return data

def format_leaderboard_text(data, group_id):
    if not data: return "No messages yet!"
    
    text = ""
    medals = ["🥇", "🥈", "🥉"]
    
    for idx, row in enumerate(data):
        user_id = row[0]
        name = row[1]
        count = row[2]
        
        rank = idx + 1
        medal = medals[idx] if rank <= 3 else f"{rank}."
        
        # Clean Name
        clean_name = name if name else "Unknown"
        # Keep name readable, limit to 12 chars
        if len(clean_name) > 12: clean_name = clean_name[:12] + ".."
        
        # Format number with comma (e.g., 1,245)
        count_str = f"{count:,}"
        
        # New Style: Medal 👤 Name • Count msgs
        text += f"{medal} 👤 {clean_name} • {count_str} \n"
        
    # Footer
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM message_log WHERE group_id = ?", (group_id,))
    total = c.fetchone()[0]
    conn.close()
    
    footer = f"\n📊 <b>Total Messages</b>: {total:,}"
    text += footer
    
    return text

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
    
    # New Header Style
    header = "╔════════════════════╗\n🏆 𝐂𝐇𝐀𝐓 𝐋𝐄𝐀𝐃𝐄𝐑𝐁𝐎𝐀𝐑𝐃\n╚════════════════════╝\n\n"
    
    leaderboard_text = format_leaderboard_text(data, group_id)
    
    update.message.reply_text(header + leaderboard_text, reply_markup=reply_markup, parse_mode='HTML')

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
    header = f"╔════════════════════╗\n🏆 𝐂𝐇𝐀𝐓 𝐋𝐄𝐀𝐃𝐄𝐑𝐁𝐎𝐀𝐑𝐃 ({title})\n╚════════════════════╝\n\n"
    
    leaderboard_text = format_leaderboard_text(lb_data, group_id)
    
    query.edit_message_text(text=header + leaderboard_text, reply_markup=reply_markup, parse_mode='HTML')

# --- FLASK ROUTE ---
@app.route('/')
def index():
    return "Bot is running and alive!"

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    init_db()
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("myprofile", my_profile))
    dp.add_handler(CommandHandler("rank", show_rank))
    dp.add_handler(CommandHandler("chatranking", chatranking))
    dp.add_handler(CallbackQueryHandler(leaderboard_button_callback, pattern='^lb_'))
    dp.add_handler(MessageHandler(Filters.all & ~Filters.command, track_message))
    
    updater.start_polling()
    
    flask_thread = Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': PORT})
    flask_thread.start()
    
    updater.idle()
