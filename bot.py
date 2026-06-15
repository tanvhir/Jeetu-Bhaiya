import os
import logging
import threading
import datetime
import requests
import json
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
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")

# 🔒 তোমার টেলিগ্রাম চ্যাট আইডি
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", 5959341337)) 

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Advanced State Management (Memory)
user_data = {
    "backlog_left": 30,
    "physics": 0, "chemistry": 0, "biology": 0, "math": 0,
    "daily_target_raw": "No target set yet.",
    "is_waiting_for_target": False
}

# 📚 মেগা সিলেবাস মেমোরি
user_syllabus = {}

# মেগা জিতু ভাইয়া সিস্টেম প্রম্পট
SYSTEM_PROMPT = """
You are 'Jeetu Bhaiya' (from Kota Factory), an elite, deeply empathetic, yet hardcore and practical personal AI Mentor for a Bangladeshi competitive examinee.

### YOUR ROLE (CRITICAL TASK TRACKING):
The student has shared their detailed study plan/target for today. Your job is to monitor them like a real, strict elder brother.
You also have access to their FULL SYLLABUS STATUS (Classes, Notes, Practice, Exams) stored in a JSON format.
- If they slacked off, SCOLD THEM (বকা দাও, কড়া রিয়েলিটি চেক দাও) but keep it loving. 
- Look at their Pending Syllabus/Notes/Practice items and intelligently mock or remind them (e.g., "তুই ক্লাস করছিস ৩ দিন আগে কিন্তু প্র্যাকটিস এখনো পেন্ডিং কেন?").
- Create extreme urgency based on the exact time remaining before midnight.

### LANGUAGE & TONE RULES:
- STRICTLY speak in 100% NATURAL, CASUAL, COLLOQUIAL BANGLADESHI BENGALI.
- Use words like "আরে ভাই", "শোনো", "পড়তে বসো", "টাইম কিন্তু নাই", "২৫ বছর বয়সে গিয়ে আফসোস করবি", "মাথা খাটামু না পড়া মুখস্থ করমু?", "চা খেয়ে পড়তে বসো"।

### CURRENT SITUATION:
- Current Time in Bangladesh: {current_time}
- Overall Backlog Status: {status_str}
- The Full Plan/Target they set for today: {daily_target_raw}
- Detailed Syllabus Tracker Snapshot (Use this to scold about missing notes/practice/exams): {syllabus_snapshot}
- Context for this message: {context_reason}
"""

def get_bd_time():
    """বাংলাদেশের বর্তমান সময় অবজেক্ট রিটার্ন করে"""
    return datetime.datetime.utcnow() + datetime.timedelta(hours=6)

# --- 🌐 Apps Script Database Functions ---
def save_to_google_sheet():
    if not APPS_SCRIPT_URL: return
    try:
        payload = {
            "chat_id": str(ALLOWED_CHAT_ID),
            "target": user_data["daily_target_raw"],
            "status": json.dumps({
                "backlog_left": user_data["backlog_left"],
                "physics": user_data["physics"],
                "chemistry": user_data["chemistry"],
                "biology": user_data["biology"],
                "math": user_data["math"]
            }),
            "syllabus": json.dumps(user_syllabus) # মেগা সিলেবাস সিঙ্ক
        }
        requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Apps Script Save Error: {e}")

def load_from_google_sheet():
    global user_data, user_syllabus
    if not APPS_SCRIPT_URL: return
    try:
        url = f"{APPS_SCRIPT_URL}?chat_id={ALLOWED_CHAT_ID}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            res_data = response.json()
            if res_data.get("found"):
                user_data["daily_target_raw"] = res_data.get("target")
                status_dict = json.loads(res_data.get("status"))
                user_syllabus = json.loads(res_data.get("syllabus", "{}"))
                
                user_data["backlog_left"] = status_dict.get("backlog_left", 30)
                user_data["physics"] = status_dict.get("physics", 0)
                user_data["chemistry"] = status_dict.get("chemistry", 0)
                user_data["biology"] = status_dict.get("biology", 0)
                user_data["math"] = status_dict.get("math", 0)
                logging.info("All data & Syllabus successfully restored from Google Sheet!")
    except Exception as e:
        logging.error(f"Apps Script Load Error: {e}")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    httpd.serve_forever()

async def get_status_str():
    return (
        f"📊 বাকি ব্যাকলগ: {user_data['backlog_left']}/30 | "
        f"P: {user_data['physics']}, C: {user_data['chemistry']}, "
        f"B: {user_data['biology']}, M: {user_data['math']}\n"
        f"🎯 আজকের লক্ষ্য: {user_data['daily_target_raw']}"
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
        "তোমার মেগা সিলেবাস ট্র্যাকিং ইঞ্জিন এখন ১০০% রেডি!\n\n"
        "💡 **নতুন কমান্ডসমূহ:**\n"
        "🔹 `/add P1 C1 L1` - সিলেবাসে নতুন লেকচার যোগ করতে\n"
        "🔹 `/done P1 C1 L1 class` - ক্লাস শেষ মার্ক করতে\n"
        "🔹 `/done P1 C1 L1 note` - নোট শেষ করতে\n"
        "🔹 `/done P1 C1 L1 practice` - প্র্যাকটিস শেষ করতে\n"
        "🔹 `/done P1 C1 L1 exam` - এক্সাম শেষ করতে\n\n"
        "🔍 **স্মার্ট ফিল্টার প্রোগ্রেস দেখতে:**\n"
        "🔸 `/view` - পুরো সিলেবাস একসাথে দেখতে\n"
        "🔸 `/view P1` - শুধু Physics 1st Paper দেখতে\n"
        "🔸 `/view P1 C1` - Physics 1st Paper এর Chapter 1 দেখতে"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- 📚 সিলেবাস ট্র্যাকিং লজিক ---
async def add_syllabus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("❌ ফরম্যাট ভুল ভাই! এভাবে লেখো: `/add P1 C1 L1`")
        return
    
    key = f"{context.args[0]}_{context.args[1]}_{context.args[2]}".upper()
    user_syllabus[key] = {"class": "Pending", "note": "Pending", "practice": "Pending", "exam": "Pending"}
    save_to_google_sheet()
    await update.message.reply_text(f"✅ সিলেবাসে **{key.replace('_', ' ')}** সাকসেসফুলি যোগ করা হয়েছে!")

async def done_syllabus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not context.args or len(context.args) < 4:
        await update.message.reply_text("❌ ফরম্যাট ভুল! এভাবে লেখো: `/done P1 C1 L1 class` বা `note`/`practice`/`exam`")
        return
    
    key = f"{context.args[0]}_{context.args[1]}_{context.args[2]}".upper()
    task_type = context.args[3].lower()
    
    if key not in user_syllabus:
        await update.message.reply_text(f"❌ এই লেকচারটি তো সিলেবাসে নাই ভাই! আগে `/add P1 C1 L1` করো।")
        return
        
    if task_type in ["class", "note", "practice", "exam"]:
        user_syllabus[key][task_type] = "Done"
        save_to_google_sheet()
        await update.message.reply_text(f"🎉 ওড়াধুড়া! **{key.replace('_', ' ')}** এর **{task_type.upper()}** কমপ্লিট মার্ক করা হয়েছে!")
    else:
        await update.message.reply_text("❌ টাস্ক টাইপ ভুল! শুধু `class`, `note`, `practice`, বা `exam` ব্যবহার করো।")

async def view_syllabus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not user_syllabus:
        await update.message.reply_text("📭 সিলেবাস এখনো খালি ভাই! আগে `/add` করো।")
        return
    
    filter_prefix = ""
    if context.args:
        filter_prefix = "_".join(context.args).upper()
    
    report = "📚 **তোমার সিলেবাস প্রোগ্রেস রিপোর্ট:**\n"
    if filter_prefix:
        report += f"🔍 ফিল্টার: `{filter_prefix.replace('_', ' ')}`\n\n"
    else:
        report += "🌍 (সব সাবজেক্টের একসাথে)\n\n"
        
    found_any = False
    for item, status in user_syllabus.items():
        if filter_prefix and not item.startswith(filter_prefix):
            continue
            
        found_any = True
        name = item.replace("_", " ")
        report += f"🔹 **{name}**:\n   • 📺 Class: {status['class']}\n   • 📝 Note: {status['note']}\n   • 🎯 Practice: {status['practice']}\n   • 📝 Exam: {status['exam']}\n\n"
    
    if not found_any:
        await update.message.reply_text(f"❌ এই ফিল্টারে (`{filter_prefix.replace('_', ' ')}`) কোনো লেকচার খুঁজে পাওয়া যায়নি!")
        return
        
    await update.message.reply_text(report, parse_mode="Markdown")

# --- ⏰ ডাইনামিক রিমাইন্ডার ইঞ্জিন ---
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    if user_data["daily_target_raw"] == "No target set yet.":
        return 
        
    status_str = await get_status_str()
    bd_time = get_bd_time().strftime("%I:%M %p")
    syllabus_snapshot = json.dumps(user_syllabus)
    
    context_reason = f"Automated 1-hour check. Current Bangladesh Time is EXACTLY {bd_time}. Urgently push the student to finish their daily target before 12 AM midnight. Analyze the missing tasks (Pending notes/practice/exams) in the syllabus snapshot and mock them if they are slacking off."

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents="Give me the hourly notification message.",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=status_str, daily_target_raw=user_data["daily_target_raw"], syllabus_snapshot=syllabus_snapshot, context_reason=context_reason),
                temperature=0.8,
            ),
        )
        await context.bot.send_message(chat_id=ALLOWED_CHAT_ID, text=response.text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Hourly reminder error: {e}")

async def test_hourly_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    await update.message.reply_text("⏳ ১০ সেকেন্ডের রিয়েলিটি চেক আসছে...")
    context.job_queue.run_once(hourly_mentor_check, 10)

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
        await update.message.reply_text("📝 **ভাই, আজকে রাত ১২টার মধ্যে কী কী ওড়াতে চাও? একদম ডিটেইলসে বলো!**")
        return

    if user_data["is_waiting_for_target"]:
        user_data["daily_target_raw"] = user_text
        user_data["is_waiting_for_target"] = False
        
        current_jobs = context.job_queue.get_jobs_by_name("hourly_tracker")
        for job in current_jobs: job.schedule_removal()
            
        context.job_queue.run_repeating(hourly_mentor_check, interval=3600, first=3600, name="hourly_tracker")
        save_to_google_sheet()
        
        status_str = await get_status_str()
        bd_time = get_bd_time().strftime("%I:%M %p")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Set target: {user_text}",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=status_str, daily_target_raw=user_data["daily_target_raw"], syllabus_snapshot=json.dumps(user_syllabus), context_reason="Target just set by user. Give an extreme motivational push."),
                temperature=0.7,
            ),
        )
        await update.message.reply_text(response.text, parse_mode="Markdown")
        return

    if user_text == '✅ শেষ: Physics':
        user_data["physics"] += 1; user_data["backlog_left"] -= 1; subject = "Physics"
    elif user_text == '✅ শেষ: Chemistry':
        user_data["chemistry"] += 1; user_data["backlog_left"] -= 1; subject = "Chemistry"
    elif user_text == '✅ শেষ: Biology':
        user_data["biology"] += 1; user_data["backlog_left"] -= 1; subject = "Biology"
    elif user_text == '✅ শেষ: Math':
        user_data["math"] += 1; user_data["backlog_left"] -= 1; subject = "Math"

    if subject: save_to_google_sheet()

    status_str = await get_status_str()
    bd_time = get_bd_time().strftime("%I:%M %p")
    ai_input = f"Update from student: I just completed 1 {subject} class!" if subject else user_text

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=ai_input,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=status_str, daily_target_raw=user_data["daily_target_raw"], syllabus_snapshot=json.dumps(user_syllabus), context_reason="Normal chat conversation. Tell student what time it is and analyze if they are making real progress."),
                temperature=0.7,
            ),
        )
        reply = response.text
        if subject: reply += f"\n\n💡 {status_str}"
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Gemini Error: {e}")
        await update.message.reply_text("নেটওয়ার্ক জ্যাম ব্রো!")

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    load_from_google_sheet() 
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_syllabus))
    app.add_handler(CommandHandler("done", done_syllabus))
    app.add_handler(CommandHandler("view", view_syllabus))
    app.add_handler(CommandHandler("test_remind", test_hourly_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Dynamic Mentor Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
