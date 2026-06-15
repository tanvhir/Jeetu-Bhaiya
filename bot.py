import os
import logging
import threading
import datetime
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# API Keys & Security Configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# 🔒 এখানে ১২৩৪৫৬৭৮৯ কেটে তোমার নিজের চ্যাট আইডি বসাও (তাহলে আর লক দেখাবে না)
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", 123456789)) 

# Initialize Groq Client
groq_client = Groq(api_key=GROQ_API_KEY)

# State Management (Memory)
user_data = {
    "backlog_left": 30,
    "physics": 0,
    "chemistry": 0,
    "biology": 0,
    "math": 0,
    "daily_target": "No target set yet for today."
}

# পারফেক্ট খাঁটি বাংলা প্রম্পট ও চ্যাট এক্সাম্পল
SYSTEM_PROMPT = """
You are 'Khayalamu', an elite personal AI Mentor for a Bangladeshi student preparing for competitive exams. 

Current Stats of the student:
{status_str}

### LANGUAGE & TONE RULES:
- STRICTLY SPEAK IN 100% NATURAL, CASUAL, COLLOQUIAL BANGLADESHI BENGALI (খাঁটি বাংলা ভাষা ও ফন্ট)।
- NEVER mix Hindi/Urdu words. Never use Google-translated words like "আহাইন্ন", "আওআমায়ের", "শিক্ষা সর্বোচ্চ আছে"।
- Speak exactly like a real Bangladeshi elder brother or close mentor guiding a younger brother. Use terms like "আরে ভাই", "শোনো", "পড়তে বসো", "ফাঁকিবাজি বন্ধ করো", "চিল করো"।

### FEW-SHOT EXAMPLES (How you must reply):
User: vallagtise na ki korbo?
AI: আরে ভাই, পড়তে কি সবসময় ভালো লাগে? মনকে একটু শক্ত করো। ফোনটা দূরে রেখে চোখে-মুখে পানি দিয়ে আসো। ৫ মিনিট একটু হেঁটে এসে আবার টেবিলে বসো। আজকের লক্ষ্য পূরণ করতে হবে তো!

User: tired lage re bhai, break chai.
AI: ঠিক আছে ভাই, একটানা পড়লে টায়ার্ড লাগা স্বাভাবিক। একটা ১৫ মিনিটের কড়া ব্রেক নাও। একটু চা খেয়ে আসতে পারো, কিন্তু কোনোভাবেই সোশ্যাল মিডিয়া স্ক্রোল করা যাবে না। ১৫ মিনিট পর এসে আমাকে জানাও!
"""

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print(f"Dummy server running on port {port}...")
    httpd.serve_forever()

async def get_status_str():
    total_done = 30 - user_data["backlog_left"]
    return (
        f" ═══【STATUS】═══\n\n"
        f"🎧 Total Backlog Left: {user_data['backlog_left']}/30\n"
        f"🎗 Classes Completed: {total_done}\n\n"
        f"📚 Subject-wise Progress:\n"
        f" ├  Physics: {user_data['physics']}\n"
        f" ├ Chemistry: {user_data['chemistry']}\n"
        f" ├ Biology: {user_data['biology']}\n"
        f" └ Math: {user_data['math']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 Today's Target: {user_data['daily_target']}"
    )

def get_main_keyboard():
    keyboard = [
        ['📊 স্ট্যাটাস চেক', '🎯 আজকের টার্গেট সেট'],
        ['✅ শেষ: Physics', '✅ শেষ: Chemistry'],
        ['✅ শেষ: Biology', '✅ শেষ: Math']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        await update.message.reply_text("❌ দুঃখিত ভাই! এই বোটটি সম্পূর্ণ ব্যক্তিগত।")
        return

    welcome_msg = (
        "👋 **আসসালামু আলাইকুম ভাই! আমি তোমার এআই মেন্টর 'Khayalamu'।**\n\n"
        "তোমার ৩০টা ক্লাসের ব্যাকলগ শেষ করার মিশনে আমি তোমার সাথে আছি।\n"
        "👇 বাটন চাপো আর পড়ালেখা শুরু করো:"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- FIXED REMINDER CODES ---
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    status_str = await get_status_str()
    reminder_msg = (
        f"🚨 **ভাই! আজকের টার্গেটের কী অবস্থা?**\n\n"
        f"🏆 *আজকের লক্ষ্য ছিল:* `{user_data['daily_target']}`\n\n"
        f"ফাঁকিবাজি না করে দ্রুত পড়া শেষ করো! কোনো ক্লাস শেষ হলে নিচের বাটন চেপে আপডেট জানিয়ে দাও।\n\n"
        f"{status_str}"
    )
    try:
        await context.bot.send_message(chat_id=ALLOWED_CHAT_ID, text=reminder_msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Reminder send failed: {e}")

async def test_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    await update.message.reply_text("⏳ রিমাইন্ডার ইঞ্জিন টেস্ট করা হচ্ছে... ঠিক ১০ সেকেন্ড পর বোট নিজে থেকে নোটিফিকেশন পাঠাবে।")
    context.job_queue.run_once(send_reminder, 10)
# ----------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Security Lock Check
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        await update.message.reply_text("❌ এই বোটটি লক করা আছে।")
        return

    user_text = update.message.text
    subject = None

    if user_text == '📊 স্ট্যাটাস চেক':
        status = await get_status_str()
        await update.message.reply_text(status, parse_mode="Markdown")
        return

    elif user_text == '🎯 আজকের টার্গেট সেট':
        user_data["daily_target"] = "Waiting for your target..."
        await update.message.reply_text("📝 **আজকে তোমার টার্গেট কী ভাই?**\nঠিকঠাক লিখে পাঠাও (যেমন: Physics Ch 1, Chem Lecture 1) — আমি মনে রাখব!")
        return

    if user_data["daily_target"] == "Waiting for your target...":
        user_data["daily_target"] = user_text
        await update.message.reply_text(f"🚀 **টার্গেট সেট হয়ে গেছে ভাই!**\n\n🏆 *আজকের টার্গেট:* `{user_text}`\n\nআমি মনে রাখলাম। এবার ফাঁকিবাজি না করে ধুমায়া পড়া শেষ করো!")
        return

    if user_text == '✅ শেষ: Physics':
        user_data["physics"] += 1
        user_data["backlog_left"] -= 1
        subject = "Physics"
    elif user_text == '✅ শেষ: Chemistry':
        user_data["chemistry"] += 1
        user_data["backlog_left"] -= 1
        subject = "Chemistry"
    elif user_text == '✅ শেষ: Biology':
        user_data["biology"] += 1
        user_data["backlog_left"] -= 1
        subject = "Biology"
    elif user_text == '✅ শেষ: Math':
        user_data["math"] += 1
        user_data["backlog_left"] -= 1
        subject = "Math"

    status_str = await get_status_str()
    ai_input = f"I just finished 1 {subject} class, including notes, practice, and exam!" if subject else user_text

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.format(status_str=status_str)},
                {"role": "user", "content": ai_input}
            ],
            model="qwen-2.5-32b", # <--- Groq-এর অফিশিয়াল সঠিক Qwen মডেল আইডি সেট করা হলো
        )
        reply = chat_completion.choices[0].message.content
        if subject:
            reply += f"\n\n{status_str}"
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Groq Error: {e}")
        if subject:
            await update.message.reply_text(f"✅ {subject} এর প্রোগ্রেস সেভ হইছে ভাই!\n\n{status_str}")
        else:
            await update.message.reply_text("🤖 'Khayalamu' ভাবতেছে... কিন্তু Groq API লাইনে পাচ্ছে না।")

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # রিমাইন্ডার শিডিউল
    app.job_queue.run_daily(send_reminder, time=datetime.time(hour=9, minute=0))   # 3:00 PM BD
    app.job_queue.run_daily(send_reminder, time=datetime.time(hour=15, minute=0)) # 9:00 PM BD

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test_remind", test_reminder_command)) 
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running with Fixed Qwen Engine...")
    app.run_polling()

if __name__ == '__main__':
    main()
