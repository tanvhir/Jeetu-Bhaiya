import os
import logging
import threading
import datetime
import requests
import json
import re
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

# Advanced State Management
user_data = {
    "backlog_left": 30,
    "physics": 0, "chemistry": 0, "biology": 0, "math": 0,
    "daily_target_raw": "No target set yet.",
    "is_waiting_for_target": False
}

# 📚 মেগা সিলেবাস মেমোরি
user_syllabus = {}

SYSTEM_PROMPT = """
You are 'Jeetu Bhaiya' (from Kota Factory), an elite, deeply empathetic, yet hardcore and practical personal AI Mentor for a Bangladeshi competitive examinee.

### YOUR ROLE (CRITICAL TASK TRACKING):
The student has shared their detailed study plan/target for today. Your job is to monitor them like a real, strict elder brother.
You also have access to their FULL SYLLABUS STATUS (Classes, Notes, Practice, Exams) stored in a compact tracker snapshot.
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
- Detailed Syllabus Tracker Snapshot: {syllabus_snapshot}
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
            "syllabus": json.dumps(user_syllabus)
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
                logging.info("All data restored successfully!")
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
        ['🚀 /status', '🎯 /plan', '📊 /report'],
        ['🛑 /stop_plan']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    welcome_msg = (
        "👋 **আসসালামু আলাইকুম ভাই! আমি তোমার মেন্টর 'Jeetu Bhaiya'**\n\n"
        "তোমার মেগা প্রফেশনাল ড্যাশবোর্ড ইঞ্জিন এখন ১০০% রেডি!\n\n"
        "💡 **সিলেবাস ম্যানেজমেন্ট কমান্ডসমূহ:**\n"
        "🔹 `/add p1 c1 l1` - একটি লেকচার যোগ করতে\n"
        "🔹 `/add p1 c1 l1-5` - একসাথে লুপে রেঞ্জ যোগ করতে (যেমন: ১ থেকে ৫)\n"
        "🔹 `/done p1 c1 l1 class` - নির্দিষ্ট আইটেম ডান করতে (`class`/`note`/`practice`/`exam`)\n"
        "🔹 `/done p1 c1 l1-5 note` - একসাথে রেঞ্জের নোট ডান করতে\n\n"
        "🔍 **স্মার্ট রিপোর্ট ও ট্র্যাকিং:**\n"
        "🔸 `/report` - পুরো সিলেবাসের প্রোগ্রেস বার ও ইনডেক্স দেখতে\n"
        "🔸 `/report p1` - ফিল্টার করে শুধু নির্দিষ্ট সাবজেক্ট দেখতে\n"
        "🔸 `/report p1 c1` - ফিল্টার করে নির্দিষ্ট চ্যাপ্টার দেখতে"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- 📚 মেগা কম্প্যাক্ট সিলেবাস ইঞ্জিন ---
def parse_lecture_range(lecture_str):
    """L1-L3 বা l1-5 থেকে লেকচারের লিস্ট জেনারেট করে"""
    lecture_str = lecture_str.upper()
    match = re.match(r"L(\d+)-L?(\d+)", lecture_str)
    if match:
        start_num = int(match.group(1))
        end_num = int(match.group(2))
        return [f"L{i}" for i in range(start_num, end_num + 1)]
    return [lecture_str]

async def add_syllabus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("❌ ফরম্যাট ভুল ভাই! এভাবে লেখো: `/add P1 C1 L1` বা `/add P1 C1 L1-5`")
        return
    
    sub = context.args[0].upper()
    ch = context.args[1].upper()
    lectures = parse_lecture_range(context.args[2])
    
    added_items = []
    for lec in lectures:
        key = f"{sub}_{ch}_{lec}"
        user_syllabus[key] = {"class": "Pending", "note": "Pending", "practice": "Pending", "exam": "Pending"}
        added_items.append(f"{sub} ∙ {ch} ∙ {lec}")
        
    save_to_google_sheet()
    await update.message.reply_text(f"✅ সিলেবাসে নতুন **{len(added_items)}টি** লেকচার সাকসেসফুলি যোগ করা হয়েছে!\n📎 `{', '.join(added_items)}`")

async def done_syllabus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not context.args or len(context.args) < 4:
        await update.message.reply_text("❌ ফরম্যাট ভুল! এভাবে লেখো: `/done P1 C1 L1 class` বা `/done P1 C1 L1-5 note`")
        return
    
    sub = context.args[0].upper()
    ch = context.args[1].upper()
    lectures = parse_lecture_range(context.args[2])
    task_type = context.args[3].lower()
    
    if task_type not in ["class", "note", "practice", "exam"]:
        await update.message.reply_text("❌ টাস্ক টাইপ ভুল! শুধু `class`, `note`, `practice`, বা `exam` ব্যবহার করো।")
        return
        
    updated_count = 0
    for lec in lectures:
        key = f"{sub}_{ch}_{lec}"
        if key in user_syllabus:
            user_syllabus[key][task_type] = "Done"
            updated_count += 1
            
    if updated_count > 0:
        save_to_google_sheet()
        await update.message.reply_text(f"🎉 ওড়াধুড়া! একসাথে **{updated_count}টি** লেকচারের **{task_type.upper()}** কমপ্লিট মার্ক করা হয়েছে!")
    else:
        await update.message.reply_text("❌ এই রেঞ্জের কোনো লেকচার সিলেবাসে খুঁজে পাওয়া যায়নি! আগে `/add` করো।")

async def view_syllabus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not user_syllabus:
        await update.message.reply_text("📭 সিলেবাস এখনো খালি ভাই! আগে `/add` করো।")
        return
    
    filter_prefix = ""
    if context.args:
        filter_prefix = "_".join(context.args).upper()
        
    # --- 📊 প্রোগ্রেস বার এবং সামারি ক্যালকুলেশন ---
    total_tasks = 0
    completed_tasks = 0
    total_lectures_count = 0
    pending_lectures_count = 0
    
    for item, status in user_syllabus.items():
        if filter_prefix and not item.startswith(filter_prefix):
            continue
        total_lectures_count += 1
        
        # ৪টা সাব-টাস্ক কাউন্ট
        lec_pending = False
        for task in ["class", "note", "practice", "exam"]:
            total_tasks += 1
            if status[task] == "Done":
                completed_tasks += 1
            else:
                lec_pending = True
                
        if lec_pending:
            pending_lectures_count += 1

    if total_lectures_count == 0:
        await update.message.reply_text(f"❌ এই ফিল্টারে (`{filter_prefix.replace('_', ' ')}`) কোনো লেকচার নেই!")
        return

    # প্রোগ্রেস বার তৈরি
    percentage = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    bar_length = 10
    filled_length = int(bar_length * percentage // 100)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    
    # ড্যাশবোর্ড হেডার ডিজাইন
    report = f"📚 **তোমার সিলেবাস প্রোগ্রেস রিপোর্ট:**\n"
    if filter_prefix:
        report += f"🔍 ফিল্টার: `{filter_prefix.replace('_', ' ')}`\n"
    report += f"📈 Progress: `[{bar}] {percentage}%`\n"
    report += f"📝 টোটাল লেকচার: `{total_lectures_count}` | ⏳ পেন্ডিং: `{pending_lectures_count}`\n"
    report += "────────────────────\n\n"
    
    # কিউট ১-লাইনের ইনডেক্স জেনারেশন
    for item, status in sorted(user_syllabus.items()):
        if filter_prefix and not item.startswith(filter_prefix):
            continue
            
        name = item.replace("_", " ∙ ")
        
        # ইমোজি বৃত্ত লজিক
        c_emoji = "🟢" if status["class"] == "Done" else "🔴"
        n_emoji = "🟢" if status["note"] == "Done" else "🔴"
        p_emoji = "🟢" if status["practice"] == "Done" else "🔴"
        e_emoji = "🟢" if status["exam"] == "Done" else "🔴"
        
        report += f"• **{name}** ➔ 📺{c_emoji} 📝{n_emoji} 🎯{p_emoji} 🏆{e_emoji}\n"
        
    await update.message.reply_text(report, parse_mode="Markdown")

# --- 🛑 রিমাইন্ডার বন্ধ করার কমান্ড ---
async def stop_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    current_jobs = context.job_queue.get_jobs_by_name("hourly_tracker")
    
    if not current_jobs:
        await update.message.reply_text("🤷‍♂️ ব্যাকগ্রাউন্ডে কোনো একটিভ প্ল্যান বা টাইমার চালু নাই ভাই!")
        return
        
    for job in current_jobs:
        job.schedule_removal()
        
    user_data["daily_target_raw"] = "No target set yet."
    save_to_google_sheet()
    await update.message.reply_text("🛑 **আজকের মতো ১ ঘণ্টার নোটিফিকেশন লুপ স্টপ করা হলো!**\nজিতু ভাইয়া তোমাকে ছুটি দিল। ভালো করে ঘুমাও, কালকে সকালে আবার ট্র্যাকে ফিরতে হবে।")

# --- ⏰ ডাইনামিক রিমাইন্ডার ইঞ্জিন ---
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    if user_data["daily_target_raw"] == "No target set yet.":
        return 
        
    status_str = await get_status_str()
    bd_time = get_bd_time().strftime("%I:%M %p")
    syllabus_snapshot = json.dumps(user_syllabus)
    
    context_reason = f"Automated 1-hour check. Current Bangladesh Time is {bd_time}. Remind the student how much time is left before midnight. Look at the pending syllabus items and mock them if they are lagging in notes/practice."

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents="Give me the hourly push notification.",
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

async def handle_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    status = await get_status_str()
    await update.message.reply_text(f"📝 **বর্তমান অবস্থা:**\n\n{status}", parse_mode="Markdown")

async def handle_plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_data["is_waiting_for_target"] = True
    await update.message.reply_text("📝 **ভাই, আজকে রাত ১২টার মধ্যে কী কী ওড়াতে চাও? একদম ডিটেইলসে বলো!**")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_text = update.message.text

    # বাটন টেক্সট ও কমান্ড ইন্টারসেপ্ট লজিক (ফর ব্যাকওয়ার্ড সামঞ্জস্য)
    if user_text in ['📊 /report', '/report']:
        await view_syllabus(update, context)
        return
    elif user_text in ['🚀 /status', '/status']:
        await handle_status_command(update, context)
        return
    elif user_text in ['🎯 /plan', '/plan']:
        await handle_plan_command(update, context)
        return
    elif user_text in ['🛑 /stop_plan', '/stop_plan']:
        await stop_plan(update, context)
        return

    # ডাইনামিক প্ল্যান ইনপুট প্রসেসিং
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
                system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=status_str, daily_target_raw=user_data["daily_target_raw"], syllabus_snapshot=json.dumps(user_syllabus), context_reason="Target just set by user."),
                temperature=0.7,
            ),
        )
        await update.message.reply_text(response.text, parse_mode="Markdown")
        return

    # নরমাল চ্যাট উইথ জিতু ভাইয়া
    status_str = await get_status_str()
    bd_time = get_bd_time().strftime("%I:%M %p")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=status_str, daily_target_raw=user_data["daily_target_raw"], syllabus_snapshot=json.dumps(user_syllabus), context_reason="Normal conversation."),
                temperature=0.7,
            ),
        )
        await update.message.reply_text(response.text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Gemini Error: {e}")
        await update.message.reply_text("নেটওয়ার্ক জ্যাম ব্রো!")

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    load_from_google_sheet() 
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", handle_status_command))
    app.add_handler(CommandHandler("plan", handle_plan_command))
    app.add_handler(CommandHandler("report", view_syllabus))
    app.add_handler(CommandHandler("add", add_syllabus))
    app.add_handler(CommandHandler("done", done_syllabus))
    app.add_handler(CommandHandler("stop_plan", stop_plan))
    app.add_handler(CommandHandler("test_remind", test_hourly_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Mega Upgraded Mentor Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
