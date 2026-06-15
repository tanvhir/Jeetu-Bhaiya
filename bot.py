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
    "daily_target_raw": "No target set yet.",
    "current_state": "NORMAL"  # স্টেটসমূহ: NORMAL, WAITING_FOR_TARGET, WAITING_FOR_ADD, WAITING_FOR_CLASS, WAITING_FOR_NOTE, WAITING_FOR_PRACTICE, WAITING_FOR_EXAM
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
    """বাংলাদেশের বর্তমান সময় অবজেক্ট রিটার্ন করে"""
    return datetime.datetime.utcnow() + datetime.timedelta(hours=6)

# --- 📊 ডাইনামিক সিলেবাস ও ব্যাকলগ অ্যানালিটিক্স ইঞ্জিন ---
def calculate_backlog_metrics():
    """user_syllabus থেকে রিয়েল-টাইম ব্যাকলগ ও সাবজেক্ট ওয়াইজ পেন্ডিং লেকচার হিসাব করে"""
    total_backlogs = 0
    sub_counts = {"P": 0, "C": 0, "B": 0, "M": 0}
    
    for item, status in user_syllabus.items():
        sub_part = item.split("_")[0].upper()
        sub_key = sub_part[0] if sub_part[0] in sub_counts else None
        
        is_pending_lecture = False
        for task in ["class", "note", "practice", "exam"]:
            if status.get(task, "Pending") == "Pending":
                is_pending_lecture = True
                break
                
        if is_pending_lecture:
            total_backlogs += 1
            if sub_key:
                sub_counts[sub_key] += 1
                
    return total_backlogs, sub_counts

async def get_status_str():
    total_backlogs, sub_counts = calculate_backlog_metrics()
    return (
        f"বাকি ব্যাকলগ: {total_backlogs}টি লেকচার | "
        f"P: {sub_counts['P']}, C: {sub_counts['C']}, "
        f"B: {sub_counts['B']}, M: {sub_counts['M']}\n"
        f"আজকের লক্ষ্য: {user_data['daily_target_raw']}"
    )

# --- 🌐 Apps Script Database Sync Engine (Fixed Capitalization Bug) ---
def save_to_google_sheet():
    if not APPS_SCRIPT_URL: return
    try:
        # শিটের কলামের সাথে ১০০% ম্যাচ করতে ক্যাপিটাল লেটার (Class, Note, Practice, Exam) দিয়ে পাঠানো হচ্ছে
        payload = {
            "chat_id": str(ALLOWED_CHAT_ID),
            "target": user_data["daily_target_raw"],
            "syllabus_rows": [
                {
                    "lecture_key": key,
                    "class": status.get("class", "Pending"),
                    "note": status.get("note", "Pending"),
                    "practice": status.get("practice", "Pending"),
                    "exam": status.get("exam", "Pending")
                }
                for key, status in user_syllabus.items()
            ]
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
                user_data["daily_target_raw"] = res_data.get("target", "No target set yet.")
                
                rows = res_data.get("syllabus_rows", [])
                new_syllabus = {}
                for row in rows:
                    key = row.get("lecture_key")
                    if key:
                        # 💡 ফিক্স: শিটে কলামের নাম 'Class' নাকি 'class' তা ডাইনামিকালি হ্যান্ডেল করা হয়েছে
                        new_syllabus[key] = {
                            "class": row.get("Class") or row.get("class") or "Pending",
                            "note": row.get("Note") or row.get("note") or "Pending",
                            "practice": row.get("Practice") or row.get("practice") or "Pending",
                            "exam": row.get("Exam") or row.get("exam") or "Pending"
                        }
                user_syllabus = new_syllabus
                logging.info("Syllabus fully loaded and case-insensitive matching resolved!")
    except Exception as e:
        logging.error(f"Apps Script Load Error: {e}")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    httpd.serve_forever()

# --- ⌨️ কিবোর্ড লেআউট জেনারেটর ---
def get_main_keyboard():
    keyboard = [
        ['Check Status', 'Set Target', 'Stop Reminders', 'Syllabus Report'],
        ['Manage Syllabus']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_syllabus_keyboard():
    keyboard = [
        ['Add New Lecture', 'Mark Class Done'],
        ['Mark Note Done', 'Mark Practice Done'],
        ['Mark Exam Done'],
        ['Back to Main Menu']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_data["current_state"] = "NORMAL"
    welcome_msg = (
        "👋 **আসসালামু আলাইকুম ভাই! আমি তোমার মেন্টর 'Jeetu Bhaiya'**\n\n"
        "গুগল শিটের ক্যাপিটাল কলাম লজিক এবং প্রোগ্রেস বার সিস্টেম পারফেক্টলি ফিক্স করে দিয়েছি। ডেটা এখন লাইভ সিঙ্ক হচ্ছে!\n\n"
        "🎮 **বাটন গাইড:**\n"
        "🔹 ১ম লাইনের ৪টি বাটন দিয়ে ডাইরেক্ট অ্যাকশন নিতে পারবে।\n"
        "🔹 `Manage Syllabus` বাটন চাপলে সাব-মেনু অন হবে।"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- 📚 মেগা কম্প্যাক্ট সিলেবাস রেঞ্জ পার্সার ---
def parse_lecture_range(lecture_str):
    lecture_str = lecture_str.upper().strip()
    match = re.match(r"L(\d+)-L?(\d+)", lecture_str)
    if match:
        start_num = int(match.group(1))
        end_num = int(match.group(2))
        return [f"L{i}" for i in range(start_num, end_num + 1)]
    return [lecture_str]

def extract_lecture_details(text):
    parts = text.strip().split()
    if len(parts) < 3:
        return None, None, None
    sub = parts[0].upper()
    ch = parts[1].upper()
    if not ch.startswith("CH") and ch[0].isdigit():
        ch = f"CH{ch}"
    lectures = parse_lecture_range(parts[2])
    return sub, ch, lectures

async def view_syllabus(update: Update, context_tg: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not user_syllabus:
        await update.message.reply_text("📭 সিলেবাস এখনো খালি ভাই! আগে `Manage Syllabus` -> `Add New Lecture` করো।")
        return
    
    total_tasks = 0
    completed_tasks = 0
    total_lectures_count = 0
    pending_lectures_count = 0
    
    for item, status in user_syllabus.items():
        total_lectures_count += 1
        lec_pending = False
        for task in ["class", "note", "practice", "exam"]:
            total_tasks += 1
            if status.get(task, "Pending") == "Done":
                completed_tasks += 1
            else:
                lec_pending = True
                
        if lec_pending:
            pending_lectures_count += 1

    percentage = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    bar_length = 10
    filled_length = int(bar_length * percentage // 100)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    
    report = f"📚 **তোমার সিলেবাস প্রোগ্রেস রিপোর্ট:**\n"
    report += f"📈 Progress: `[{bar}] {percentage}%`\n"
    report += f"📝 টোটাল লেকচার: `{total_lectures_count}` | ⏳ পেন্ডিং ব্যাকলগ: `{pending_lectures_count}`\n"
    report += "────────────────────\n\n"
    
    for item, status in sorted(user_syllabus.items()):
        name = item.replace("_", " ∙ ")
        c_emoji = "🟢" if status.get("class", "Pending") == "Done" else "🔴"
        n_emoji = "🟢" if status.get("note", "Pending") == "Done" else "🔴"
        p_emoji = "🟢" if status.get("practice", "Pending") == "Done" else "🔴"
        e_emoji = "🟢" if status.get("exam", "Pending") == "Done" else "🔴"
        
        report += f"• **{name}** ➔ 📺{c_emoji} 📝{n_emoji} 🎯{p_emoji} 🏆{e_emoji}\n"
        
    await update.message.reply_text(report, parse_mode="Markdown")

async def stop_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    current_jobs = context.job_queue.get_jobs_by_name("hourly_tracker")
    
    for job in current_jobs:
        job.schedule_removal()
        
    user_data["daily_target_raw"] = "No target set yet."
    user_data["current_state"] = "NORMAL"
    save_to_google_sheet()
    await update.message.reply_text(
        "🛑 **আজকের মতো ১ ঘণ্টার নোটিফিকেশন লুপ স্টপ করা হলো!**\nজিতু ভাইয়া তোমাকে ছুটি দিল। ভালো করে ঘুমাও, কালকে সকালে আবার ট্র্যাকে ফিরতে হবে।",
        reply_markup=get_main_keyboard()
    )

# --- ⏰ ডাইনামিক রিমাইন্ডার ইঞ্জিন ---
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    if user_data["daily_target_raw"] == "No target set yet.":
        return 
        
    status_str = await get_status_str()
    bd_time = get_bd_time().strftime("%I:%M %p")
    syllabus_snapshot = json.dumps(user_syllabus)
    
    context_reason = f"Automated 1-hour check. Current Bangladesh Time is {bd_time}. Remind the student how much time is left before midnight."

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

# --- 💬 মেসেজ রাউটার অ্যান্ড স্টেট-মেশিন ইঞ্জিন ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_text = update.message.text.strip()

    # ----------------------------------------------------
    # ১. মেইন মেনু ও সাব-মেনু বাটন ট্র্যাকিং
    # ----------------------------------------------------
    if user_text == 'Check Status':
        total_tasks = 0
        completed_tasks = 0
        for item, status in user_syllabus.items():
            for task in ["class", "note", "practice", "exam"]:
                total_tasks += 1
                if status.get(task, "Pending") == "Done":
                    completed_tasks += 1
        
        percentage = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        bar_length = 10
        filled_length = int(bar_length * percentage // 100)
        bar = "█" * filled_length + "░" * (bar_length - filled_length)
        
        status = await get_status_str()
        status_msg = f"📝 **বর্তমান অবস্থা:**\n📈 Progress: `[{bar}] {percentage}%`\n\n{status}"
        return await update.message.reply_text(status_msg, parse_mode="Markdown")
        
    elif user_text == 'Set Target':
        user_data["current_state"] = "WAITING_FOR_TARGET"
        return await update.message.reply_text("📝 **ভাই, আজকে রাত ১২টার মধ্যে কী কী ওড়াতে চাও? একদম ডিটেইলসে বলো!**")
        
    elif user_text == 'Syllabus Report':
        return await view_syllabus(update, context)
        
    elif user_text == 'Stop Reminders':
        return await stop_plan(update, context)
        
    elif user_text == 'Manage Syllabus':
        user_data["current_state"] = "NORMAL"
        return await update.message.reply_text("📚 **সিলবাস ম্যানেজমেন্ট সাব-মেনু:**\nনিচের বাটন সিলেক্ট করে পরের মেসেজে লেকচার কোড দাও।", reply_markup=get_syllabus_keyboard())
        
    elif user_text == 'Back to Main Menu':
        user_data["current_state"] = "NORMAL"
        return await update.message.reply_text("🔙 প্রধান মেনুতে ফিরে আসা হয়েছে ভাই।", reply_markup=get_main_keyboard())

    # সাব-মেনুর স্টেট ট্রিগারসমূহ
    elif user_text == 'Add New Lecture':
        user_data["current_state"] = "WAITING_FOR_ADD"
        return await update.message.reply_text("📝 কোন লেকচার যোগ করবা ভাই? সাবজেক্ট, চ্যাপ্টার আর লেকচার রেঞ্জ দাও।\n\n💡 উদাহরণ: `P1 C6 L1-5` বা `M2 C3 L1`")
        
    elif user_text == 'Mark Class Done':
        user_data["current_state"] = "WAITING_FOR_CLASS"
        return await update.message.reply_text("📺 কোন লেকচারের ক্লাস শেষ করেছ? কোড দাও।\n\n💡 উদাহরণ: `P1 C6 L1-5`")
        
    elif user_text == 'Mark Note Done':
        user_data["current_state"] = "WAITING_FOR_NOTE"
        return await update.message.reply_text("📝 কোন লেকচারের নোট শেষ করেছ? কোড দাও।\n\n💡 উদাহরণ: `P1 C6 L1-5`")
        
    elif user_text == 'Mark Practice Done':
        user_data["current_state"] = "WAITING_FOR_PRACTICE"
        return await update.message.reply_text("🎯 কোন লেকচারের প্র্যাকটিস বুক সলভ করেছ? কোড দাও।\n\n💡 উদাহরণ: `P1 C6 L1-5`")
        
    elif user_text == 'Mark Exam Done':
        user_data["current_state"] = "WAITING_FOR_EXAM"
        return await update.message.reply_text("🏆 কোন লেকচারের এক্সাম কমপ্লিট করেছ ভাই? কোড দাও।\n\n💡 উদাহরণ: `P1 C6 L1-5`")

    # ----------------------------------------------------
    # ২. স্টেটের ওপর ভিত্তি করে ডাইনামিক ইনপুট প্রসেসিং
    # ----------------------------------------------------
    current_state = user_data["current_state"]

    if current_state == "WAITING_FOR_TARGET":
        user_data["daily_target_raw"] = user_text
        user_data["current_state"] = "NORMAL"
        
        current_jobs = context.job_queue.get_jobs_by_name("hourly_tracker")
        for job in current_jobs: job.schedule_removal()
            
        context.job_queue.run_repeating(hourly_mentor_check, interval=3600, first=3600, name="hourly_tracker")
        save_to_google_sheet()
        
        status_str = await get_status_str()
        bd_time = get_bd_time().strftime("%I:%M %p")
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"Set target: {user_text}",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=status_str, daily_target_raw=user_data["daily_target_raw"], syllabus_snapshot=json.dumps(user_syllabus), context_reason="Target just set by user."),
                    temperature=0.7,
                ),
            )
            await update.message.reply_text(response.text, parse_mode="Markdown", reply_markup=get_main_keyboard())
        except Exception as e:
            logging.error(f"Gemini Target Error: {e}")
            await update.message.reply_text("আজকের টার্গেট সেট হয়েছে ভাই! পড়তে বসে যাও!", reply_markup=get_main_keyboard())
        return

    elif current_state == "WAITING_FOR_ADD":
        sub, ch, lectures = extract_lecture_details(user_text)
        if not sub:
            return await update.message.reply_text("❌ ফরম্যাট ভুল ভাই! এভাবে লেখো: `P1 C6 L1-5` বা `P1 C6 L1`")
        
        added_items = []
        for lec in lectures:
            key = f"{sub}_{ch}_{lec}"
            if key not in user_syllabus:
                user_syllabus[key] = {"class": "Pending", "note": "Pending", "practice": "Pending", "exam": "Pending"}
                added_items.append(f"{sub} ∙ {ch} ∙ {lec}")
            
        user_data["current_state"] = "NORMAL"
        if added_items:
            save_to_google_sheet()
            await update.message.reply_text(f"✅ সিলেবাসে নতুন **{len(added_items)}টি** লেকচার সাকসেসফুলি যোগ করা হয়েছে!\n📎 `{', '.join(added_items)}`", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("⚠ এই লেকচারগুলো অলরেডি সিলেবাসে আছে ভাই!", reply_markup=get_main_keyboard())
        return

    elif current_state in ["WAITING_FOR_CLASS", "WAITING_FOR_NOTE", "WAITING_FOR_PRACTICE", "WAITING_FOR_EXAM"]:
        sub, ch, lectures = extract_lecture_details(user_text)
        if not sub:
            return await update.message.reply_text("❌ ফরম্যাট ভুল ভাই! এভাবে লেখো: `P1 C6 L1` বা `P1 C6 L1-5`")
            
        task_map = {
            "WAITING_FOR_CLASS": "class",
            "WAITING_FOR_NOTE": "note",
            "WAITING_FOR_PRACTICE": "practice",
            "WAITING_FOR_EXAM": "exam"
        }
        task_type = task_map[current_state]
        
        updated_count = 0
        for lec in lectures:
            key = f"{sub}_{ch}_{lec}"
            if key in user_syllabus:
                user_syllabus[key][task_type] = "Done"
                updated_count += 1
                
        user_data["current_state"] = "NORMAL"
        if updated_count > 0:
            save_to_google_sheet()
            await update.message.reply_text(f"🎉 ওড়াধুড়া! একসাথে **{updated_count}টি** লেকচারের **{task_type.upper()}** কমপ্লিট মার্ক করা হয়েছে!", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("❌ এই রেঞ্জের কোনো লেকচার সিলেবাসে খুঁজে পাওয়া যায়নি! আগে `Add New Lecture` বাটন দিয়ে লেকচারটি অ্যাড করো ভাই।", reply_markup=get_main_keyboard())
        return

    # 🚀 ৩. ওপেন ফ্রি চ্যাট রুট
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
        logging.error(f"Gemini Normal Chat Error: {e}")
        await update.message.reply_text("নেটওয়ার্ক একটু ফ্ল্যাকচুয়েট করছে ভাই! আরেকবার বলো তো?")

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    load_from_google_sheet() 
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", start)) 
    app.add_handler(CommandHandler("plan", start))
    app.add_handler(CommandHandler("report", view_syllabus))
    app.add_handler(CommandHandler("stop_plan", stop_plan))
    app.add_handler(CommandHandler("test_remind", test_hourly_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Dynamic Row-Synced Bot Engine is successfully live...")
    app.run_polling()

if __name__ == '__main__':
    main()
