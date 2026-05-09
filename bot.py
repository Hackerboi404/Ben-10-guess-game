import telebot
import json
import random
import os
from datetime import datetime
from alive import keep_alive

# CONFIGURATION
# REPLACE WITH YOUR TOKEN FROM BOTFATHER
API_TOKEN = '8619692826:AAFrNB53VkIKKfsVABakrw8kALwW1Z4KEUs'

bot = telebot.TeleBot(API_TOKEN)

# FILE PATHS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
ALIENS_FILE = os.path.join(DATA_DIR, 'aliens.json')
SCORES_FILE = os.path.join(DATA_DIR, 'scores.json')

# GAME STATE
# Dictionary to store current game state for each group/chat
# Structure: { chat_id: { 'alien': obj, 'hint_index': int, 'guessed': bool } }
games = {}

# -------------------------
# DATA HELPER FUNCTIONS
# -------------------------

def load_data(filepath):
    try:
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return {}

def save_data(filepath, data):
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving {filepath}: {e}")

def get_aliens():
    data = load_data(ALIENS_FILE)
    return data if isinstance(data, list) else []

# -------------------------
# GAME LOGIC FUNCTIONS
# -------------------------

def start_new_round(chat_id):
    aliens = get_aliens()
    if not aliens:
        return "⚠️ Omnitrix Malfunction: No alien data found!"
    
    alien = random.choice(aliens)
    games[chat_id] = {
        'alien': alien,
        'hint_index': 0,
        'guessed': False,
        'wrong_guesses': [] # Track wrong guesses to prevent spam
    }
    return None # No error

def update_score(user_id, user_name, difficulty):
    scores = load_data(SCORES_FILE)
    
    # Points based on difficulty
    points_map = {'easy': 1, 'medium': 2, 'hard': 3}
    points = points_map.get(difficulty, 1)
    
    user_key = str(user_id)
    if user_key in scores:
        scores[user_key]['score'] += points
    else:
        scores[user_key] = {'name': user_name, 'score': points}
        
    save_data(SCORES_FILE, scores)
    return scores[user_key]['score']

def get_leaderboard():
    scores = load_data(SCORES_FILE)
    if not scores:
        return "📊 No heroes ranked yet."
    
    # Sort by score descending
    sorted_scores = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
    
    text = "🏆 OMNITRIX LEADERBOARD 🏆\n\n"
    for i, (uid, data) in enumerate(sorted_scores[:10], 1):
        text += f"{i}. {data['name']} - {data['score']} pts\n"
    return text

# -------------------------
# COMMAND HANDLERS
# -------------------------

@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Only trigger in groups or private
    name = message.from_user.first_name
    text = (
        f"🟢 OMNITRIX LINK ESTABLISHED\n\n"
        f"Welcome {name} to Guess The Alien Arena ⚡\n\n"
        f"🎮 Commands:\n"
        f"/startgame - Start a new alien round\n"
        f"/hint - Get another hint\n"
        f"/score - View leaderboard\n"
        f"/skip - Skip current alien\n"
        f"/help - Game help\n\n"
        f"“It’s Hero Time!” 🔥"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=['help'])
def send_help(message):
    text = (
        "🧬 DNA GUIDE 🧬\n\n"
        "1. Use /startgame to begin.\n"
        "2. I will give a hint about an alien.\n"
        "3. Type the name of the alien to guess!\n"
        "4. Use /hint if you are stuck (fewer points!).\n"
        "5. Easy = 1pt, Medium = 2pts, Hard = 3pts.\n\n"
        "Guess the alien to save the day!"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=['startgame'])
def start_game(message):
    chat_id = message.chat.id
    error = start_new_round(chat_id)
    
    if error:
        bot.reply_to(message, error)
        return

    alien = games[chat_id]['alien']
    bot.reply_to(message, f"🧬 DNA Scan Started... Difficulty: {alien['difficulty'].upper()}")
    
    # Send first hint
    give_hint(chat_id, message.chat.id)

def give_hint(chat_id, target_id):
    if chat_id not in games:
        return
    
    game = games[chat_id]
    alien = game['alien']
    hints = alien['hints']
    index = game['hint_index']
    
    if index < len(hints):
        # Use send_message to target the specific chat (important if logic separates target)
        bot.send_message(target_id, f"💡 Hint #{index + 1}: {hints[index]}")
        game['hint_index'] += 1

@bot.message_handler(commands=['hint'])
def command_hint(message):
    chat_id = message.chat.id
    if chat_id in games:
        give_hint(chat_id, chat_id)
    else:
        bot.reply_to(message, "❌ No active transformation. Type /startgame first.")

@bot.message_handler(commands=['skip'])
def skip_round(message):
    chat_id = message.chat.id
    if chat_id in games:
        alien = games[chat_id]['alien']
        bot.reply_to(message, f"⏭️ Skipped! It was {alien['name']}.")
        start_new_round(chat_id)
        bot.send_message(chat_id, "🧬 DNA Scan Started... New Round!")
        give_hint(chat_id, chat_id)
    else:
        bot.reply_to(message, "No game active.")

@bot.message_handler(commands=['score'])
def show_score(message):
    bot.reply_to(message, get_leaderboard())

# -------------------------
# GAMEPLAY & MESSAGES
# -------------------------

@bot.message_handler(func=lambda message: True)
def handle_guess(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    user_guess = message.text.strip().lower()

    # Only process if game is active and not already guessed
    if chat_id not in games or games[chat_id]['guessed']:
        return

    game = games[chat_id]
    alien_name = game['alien']['name'].lower()
    
    # Anti-spam: Check if user already guessed this wrong
    if user_guess in game['wrong_guesses']:
        return # Ignore repeated wrong guesses

    if user_guess == alien_name:
        # CORRECT ANSWER
        game['guessed'] = True
        
        # Calculate score reduction based on hints used
        base_score_map = {'easy': 1, 'medium': 2, 'hard': 3}
        difficulty = game['alien']['difficulty']
        points = base_score_map.get(difficulty, 1)
        
        # Deduct 0.5 points for every hint beyond the first
        hints_used = game['hint_index']
        penalty = 0.5 * (hints_used - 1)
        if penalty < 0: penalty = 0
        final_points = max(1, int(points - penalty)) # Ensure at least 1 point
        
        # Manually update score to handle custom logic (or simplify by calling update_score and accepting standard points)
        # For simplicity in this demo, we will use standard update_score, 
        # but let's do a simple manual add for the logic requested.
        scores = load_data(SCORES_FILE)
        u_key = str(user_id)
        current_total = scores.get(u_key, {}).get('score', 0) + final_points
        scores[u_key] = {'name': user_name, 'score': current_total}
        save_data(SCORES_FILE, scores)

        # Success Messages
        success_msgs = ["🔥 It’s Hero Time!", "🟢 Perfect transformation!", "👽 DNA Match Complete!"]
        response = (
            f"{random.choice(success_msgs)}\n"
            f"✅ Correct! It was {game['alien']['name']}.\n"
            f"🎖️ {user_name} earned {final_points} points!"
        )
        bot.reply_to(message, response)
        
        # Auto start next round
        start_new_round(chat_id)
        bot.send_message(chat_id, "🧬 DNA Scan Started... Next Round!")
        give_hint(chat_id, chat_id)
        
    else:
        # WRONG ANSWER
        game['wrong_guesses'].append(user_guess)
        fail_msgs = ["❌ DNA mismatch", "⚠️ Wrong transformation", "💀 Omnitrix rejected that guess"]
        bot.reply_to(message, random.choice(fail_msgs))

# -------------------------
# START BOT
# -------------------------

if __name__ == '__main__':
    print("🚀 Omnitrix Bot Starting...")
    keep_alive()
    bot.infinity_polling()
