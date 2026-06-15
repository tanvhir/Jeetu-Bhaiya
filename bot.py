import os
import logging
import threading
import datetime
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# API Keys & Security Configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# 🔒 এখানে তোমার আসল টেলিগ্রাম চ্যাট আইডি বসাও
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", 5959341337)) 

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Advanced State Management (Memory)
user_data = {
    "backlog_left": 30,
    "physics": 0, "chemistry": 0, "biology": 0, "math": 0,
    "daily_target_raw": "No target set yet.",
    "target_time": None,
    "is_waiting_for_target": False
}

# মেগা জিতু ভাইয়া সিস্টেম প্রম্পট (The Ultimate Version)
SYSTEM_PROMPT = """
You are 'Jeetu Bhaiya' (from Kota Factory), an elite, deeply empathetic, yet hardcore and practical personal AI Mentor for a Bangladeshi competitive examinee.

### YOUR ROLE (CRITICAL TASK TRACKING):
The student has shared their detailed study plan/target for today. Your job is to monitor them like a real, strict elder brother.
You must analyze their progress based on what they update you. 
- If they slacked off, SCOLD THEM (বকা দাও, কড়া রিয়েলিটি চেক দাও) but keep it loving. 
- If they did partial work (e.g., half lecture done), YOU MUST REMEMBER IT and ask specifically about the remaining half in the next hourly reminder!
- Keep an eye on how many hours are left before midnight and create urgency.

### LANGUAGE & TONE RULES:
- STRICTLY speak in 100% NATURAL, CASUAL, COLLOQUIAL BANGLADESHI BENGALI (খাঁটি বাংলাদেশি হোস্টেলের সিনিয়রের মতো ইনফরমাল ভাষা)।
- NEVER use bookish or Google-translated words.
- Use words like "আরে ভাই", "শোনো", "পড়তে বসো", "টাইম কিন্তু নাই", "২৫ বছর বয়সে গিয়ে আফসোস করবি", "মাথা খাটামু না পড়া মুখস্থ করমু?", "চা খেয়ে পড়তে বসো"।
- Your philosophy: Exams are about building a character and lifestyle. Be realistic, sharp, sarcastic when they fail, and highly motivating when they achieve.

### CURRENT SITUATION:
- Overall Backlog Status: {status_str}
- The Full Plan/Target they set: {daily_target_raw}
- Context for this message: {context_reason}
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
        f"📊 বাকি ব্যাকলগ: {user_data['backlog_left']}/30 | "
        f"Physics: {user_data['physics']}, Chem: {user_data['chemistry']}, "
        f"Bio: {user_data['biology']}, Math: {user_data['math']}\n"
        f"🎯 আজকের ফুল প্ল্যান: {user_data['daily_target_raw']}"
    )

def get_main_keyboard():
    keyboard = [
        ['📊 স্ট্যাটাস চেক', '🎯 ডাইনামিক প্ল্যান সেট'],
        ['✅ শেষ: Physics', '✅ শেষ: Chemistry'],
        ['✅ শেষ: Biology', '✅ শেষ: Math']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    welcome_msg = (
        "👋 **আসসালামু আলাইকুম ভাই! আমি তোমার মেন্টর 'Jeetu Bhaiya'**\n\n"
        "এখন থেকে তুমি আমার সাথে পুরো দিনের ডিটেইলস প্ল্যান লক করতে পারবে। "
        "আমি প্রতি ১ ঘণ্টা পর পর এসে তোমার লাইফ হেল করে দেব প্রোগ্রেস জানার জন্য! 😈\n\n"
        "👇 শুরু করতে '🎯 ডাইনামিক প্ল্যান সেট' বাটনে চাপো:"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- ⏰ ডাইনামিক ১ ঘণ্টার মেন্টর রিমাইন্ডার ইঞ্জিন ---
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    """প্রতি ১ ঘণ্টা পর পর জেমিনি নিজে থেকে মেসেজ জেনারেট করে ইউজারকে নক দেবে"""
    if user_data["daily_target_raw"] == "No target set yet.":
        return # কোনো প্ল্যান সেট না থাকলে রিমাইন্ডার যাবে না
        
    status_str = await get_status_str()
    context_reason = "This is an automated 1-hour progress check. Ask the student what they have done in the last 1 hour from their plan. SCOLD them if they haven't updated you recently, remind them how many hours are left before 12 AM midnight, and intelligently cross-question their progress."

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents="Give me the hourly push notification message for the student.",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(status_str=status_str, daily_target_raw=user_data["daily_target_raw"], context_reason=context_reason),
                temperature=0.8,
            ),
        )
        await context.bot.send_message(chat_id=ALLOWED_CHAT_ID, text=response.text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Hourly reminder error: {e}")

async def test_hourly_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """টেস্ট করার জন্য ১০ সেকেন্ড পর পর নক দেওয়ার সিক্রেট কমান্ড"""
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    await update.message.reply_text("⏳ ডাইনামিক মেন্টর ইঞ্জিন অ্যাক্টিভেট হচ্ছে... ১০ সেকেন্ড পর প্রথম রিয়েলিটি চেক আসবে!")
    context.job_queue.run_once(hourly_mentor_check, 10)
# ---------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return

    user_text = update.message.text
    subject = None

    if user_text == '📊 স্ট্যাটাস চেক':
        status = await get_status_str()
        await update.message.reply_text(f"📝 **বর্তমান অবস্থা:**\n\n{status}", parse_mode="Markdown")
        return

    elif user_text == '🎯 ডাইনামিক প্ল্যান সেট':
        user_data["is_waiting_for_target"] = True
        await update.message.reply_text(
            "📝 **ভাই, আজকে রাত ১২টার মধ্যে কী কী ওড়াতে চাও? একদম ডিটেইলসে বলো!**\n\n"
            "যেমন এভাবে লেখো:\n"
            "_- Physics Lecture 3 দেখব ও নোট করব_\n"
            "_- Chem Ch 2 এর ২৫টা ম্যাথ প্র্যাকটিস করব_"
        )
        return

    # প্ল্যান সেভ করা এবং ১ ঘণ্টার লুপ চালু করা
    if user_data["is_waiting_for_target"]:
        user_data["daily_target_raw"] = user_text
        user_data["is_waiting_for_target"] = False
        
        # আগের কোনো রিমাইন্ডার জব চালু থাকলে সেটা রিমুভ করা
        current_jobs = context.job_queue.get_jobs_by_name("hourly_tracker")
        for job in current_jobs:
            job.schedule_removal()
            
        # প্রতি ১ ঘণ্টা (৩৬০০ সেকেন্ড) পর পর রিমাইন্ডার সেট করা
        context.job_queue.run_repeating(hourly_mentor_check, interval=3600, first=3600, name="hourly_tracker")
        
        status_str = await get_status_str()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"I have set my target: {user_text}. Acknowledge it like a strict mentor and tell me you will check on me every hour.",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(status_str=status_str, daily_target_raw=user_data["daily_target_raw"], context_reason="Target just set by user. Give a highly motivating acceptence speech."),
                temperature=0.7,
            ),
        )
        await update.message.reply_text(response.text, parse_mode="Markdown")
        return

    # সাবজেক্ট ম্যানুয়াল বাটন হ্যান্ডলিং
    if user_text == '✅ শেষ: Physics':
        user_data["physics"] += 1; user_data["backlog_left"] -= 1; subject = "Physics"
    elif user_text == '✅ শেষ: Chemistry':
        user_data["chemistry"] += 1; user_data["backlog_left"] -= 1; subject = "Chemistry"
    elif user_text == '✅ শেষ: Biology':
        user_data["biology"] += 1; user_data["backlog_left"] -= 1; subject = "Biology"
    elif user_text == '✅ শেষ: Math':
        user_data["math"] += 1; user_data["backlog_left"] -= 1; subject = "Math"

    status_str = await get_status_str()
    ai_input = f"Update from student: I just completed 1 {subject} class from my plan!" if subject else user_text

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=ai_input,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(status_str=status_str, daily_target_raw=user_data["daily_target_raw"], context_reason="Normal conversation/update from student. Analyze if they are doing partial work or full work, note it down in mind, and reply accordingly."),
                temperature=0.7,
            ),
        )
        reply = response.text
        if subject:
            reply += f"\n\n💡 {status_str}"
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Gemini Error: {e}")
        await update.message.reply_text("নেটওয়ার্ক জ্যাম ব্রো! একটু পরে ট্রাই কর।")

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test_remind", test_hourly_command)) # ১০ সেকেন্ডের ইনস্ট্যান্ট টেস্ট কমান্ড
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Dynamic Mentor Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
