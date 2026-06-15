import os
import logging
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# API Keys & Security Configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# 🔒 তোমার টেলিগ্রাম চ্যাট আইডি এখানে বসাও (উদা: 123456789)
# Render-এর Environment Variables-এও 'ALLOWED_CHAT_ID' নামে সেট করতে পারো।
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", 5959341337)) # <--- এখানে তোমার ID বসাও

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

SYSTEM_PROMPT = """
You are 'Khayalamu', an elite personal AI Mentor for a Bangladeshi student. The student has a backlog of 30 online classes across Physics, Chemistry, Biology, and Math.

Current Stats:
{status_str}

### LANGUAGE & TONE RULES (CRITICAL):
- ALWAYS speak in 100% PURE, NATURAL, and CASUAL BENGALI (বাংলা ফন্ট)। NEVER use English or Banglish letters.
- NEVER use broken Google-translated words or mix Hindi phrases.
- Speak EXACTLY like a real supportive Bangladeshi big brother or personal coach.
- Keep responses short, bold, and highly motivating. Use proper emojis.
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
    # Security Check
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        await update.message.reply_text("❌ দুঃখিত ভাই! এই বোটটি সম্পূর্ণ ব্যক্তিগত। আপনি এটি ব্যবহার করতে পারবেন না।")
        return

    welcome_msg = (
        "👋 **আসসালামু আলাইকুম ভাই! আমি তোমার এআই মেন্টর 'Khayalamu'।**\n\n"
        "তোমার ৩০টা ক্লাসের ব্যাকলগ শেষ করার মিশনে আমি তোমার সাথে আছি।\n"
        "👇 বাটন চাপো আর পড়ালেখা শুরু করো:"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔒 Security Check (অন্য কেউ মেসেজ দিলে এখানেই আটকে যাবে)
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        await update.message.reply_text("❌ এই বোটটি ব্যক্তিগত ব্যবহারের জন্য লক করা আছে।")
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
            model="llama-3.1-8b-instant",
        )
        reply = chat_completion.choices[0].message.content
        if subject:
            reply += f"\n\n{status_str}"
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Groq Error: {e}")
        if subject:
            await update.message.reply_text(f"✅ {subject} এর প্রোগ্রেস সেভ হইছে ভাই! কিন্তু Groq API একটু ঝামেলা করতেছে。\n\n{status_str}")
        else:
            await update.message.reply_text("🤖 'Khayalamu' ভাবতেছে... কিন্তু Groq API লাইনে পাচ্ছে না।")

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
