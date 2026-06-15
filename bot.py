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
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", 5959341337)) 

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Advanced State Management
user_data = {
    "daily_target_raw": "No target set yet.",
    "is_waiting_for_target": False
}
user_syllabus = {}

SYSTEM_PROMPT = """
You are 'Jeetu Bhaiya' (from Kota Factory), an elite, deeply empathetic, yet hardcore and practical personal AI Mentor for a Bangladeshi competitive examinee.

### YOUR ROLE (CRITICAL TASK TRACKING):
The student has shared their study plan for today. Your job is to monitor them like a real, strict elder brother.
You have access to highly filtered, optimized insights from their syllabus database:
- Overall Stats: {status_str}
- Today's Target: {daily_target_raw}
- Recent Unfinished Items: {recent_pending} (Remind them that they touched this recently but left it half-done! Tell them to finish it.)
- Spaced Repetition Recap: {recap_item} (CRITICAL: This is an item they fully completed around 30 days ago. Intelligently tell them to spend 15 minutes to RECAP/REVIEW this old topic so they don't forget it. Use logic like 'ওল্ড ইজ গোল্ড, রিভিশন না দিলে পরীক্ষার হলে কান্নাকাটি করবি!')

### LANGUAGE & TONE RULES:
- STRICTLY speak in 100% NATURAL, CASUAL, COLLOQUIAL BANGLADESHI BENGALI.
- Use words like "আরে ভাই", "শোনো", "পড়তে বসো", "টাইম কিন্তু নাই", "২৫ বছর বয়সে গিয়ে আফসোস করবি", "চা খেয়ে পড়তে বসো"।
"""

def get_bd_time():
    """বাংলাদেশের বর্তমান সময় রিটার্ন করে (ইউটিসি + ৬ ঘণ্টা)"""
    return datetime.datetime.utcnow() + datetime.timedelta(hours=6)

# --- 🧠 মেগা স্মার্ট লার্নিং অ্যান্ড স্পেসড রেপিটেশন ইঞ্জিন ---
def process_ai_insights():
    total_lectures = len(user_syllabus)
    pending_lectures = 0
    complete_lectures = 0
    
    recent_pending_list = []
    recap_list = []
    
    now = get_bd_time()
    
    for item, status in sorted(user_syllabus.items(), key=lambda x: x[1].get('last_updated', ''), reverse=True):
        tasks = [status.get("class", "Pending"), status.get("note", "Pending"), status.get("practice", "Pending"), status.get("exam", "Pending")]
        done_count = tasks.count("Done")
        
        # 📅 ক্র্যাশ-ফ্রি টাইমস্ট্যাম্প পার্সিং লজিক
        lu_str = status.get("last_updated", "")
        days_diff = 0
        if lu_str:
            try:
                # 'Tue Jun 16 2026' এর মতো অংশ আলাদা করে সহজে দিন বের করা
                parts = lu_str.split(" ")
                if len(parts) >= 4:
                    date_pure_str = f"{parts[1]} {parts[2]} {parts[3]}" # e.g., "Jun 16 2026"
                    parsed_dt = datetime.datetime.strptime(date_pure_str, "%b %d %Y")
                    days_diff = (now.date() - parsed_dt.date()).days
            except Exception as e:
                logging.error(f"Date calculation error skipped: {e}")

        if done_count == 4:
            complete_lectures += 1
            # ⏳ স্পেসড রেপিটেশন: ৩০ দিন পার হলে রিক্যাপ জোনে যাবে
            if days_diff >= 30:
                recap_list.append(item.replace("_", " "))
        else:
            pending_lectures += 1
            # 🔴 রিসেন্ট হাফ-ডান টপিক ছাঁকন লজিক
            if done_count > 0 and len(recent_pending_list) < 2:
                missing = [t.upper() for t in ["class", "note", "practice", "exam"] if status.get(t) == "Pending"]
                recent_pending_list.append(f"{item.replace('_', ' ')} (Baki: {', '.join(missing)})")

    stats_str = f"Total: {total_lectures} | Done: {complete_lectures} | Pending: {pending_lectures}"
    recent_str = ", ".join(recent_pending_list) if recent_pending_list else "None. All recent topics are fully complete!"
    recap_str = recap_list[0] if recap_list else "None. No old topics need a review loop today."
    
    return stats_str, recent_str, recap_str, total_lectures, pending_lectures, complete_lectures

# --- 🌐 Database Connections (Apps Script) ---
def save_syllabus_item(l_key, task_dict):
    if not APPS_SCRIPT_URL: return
    try:
        payload = {"chat_id": str(ALLOWED_CHAT_ID), "syllabus_update": True, "lecture_key": l_key}
        payload.update(task_dict)
        requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
    except Exception as e: 
        logging.error(f"Save Syllabus Error: {e}")

def save_target_to_sheet(target_text):
    if not APPS_SCRIPT_URL: return
    try:
        payload = {"chat_id": str(ALLOWED_CHAT_ID), "target_update": True, "target": target_text}
        requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
    except Exception as e: 
        logging.error(f"Save Target Error: {e}")

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
                user_syllabus = res_data.get("syllabus", {})
                logging.info("Synced perfectly with row-based architecture!")
    except Exception as e: 
        logging.error(f"Load Error: {e}")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('', port), SimpleHTTPRequestHandler).serve_forever()

def get_main_keyboard():
    # 🚀 একদম ক্লিন, মিনিমাল আইকন-বেসড কীবোর্ড লেআউট
    return ReplyKeyboardMarkup([['🚀 /status', '🎯 /plan', '📊 /report'], ['🛑 /stop_plan']], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    welcome = (
        "🧠 **Welcome to Elite Mentor Engine v3**\n\n"
        "সিস্টেম এখন রো-বেসড ডাটাবেজ এবং স্পেসড রেপিটেশন ট্র্যাকিং মোডে লাইভ।\n\n"
        "💡 **কমান্ড গাইড:**\n"
        "🔹 `/add P1 C1 L1-3` ➔ লুপে রেঞ্জ এড করা\n"
        "🔹 `/done P1 C1 L1 class` ➔ আইটেম সম্পন্ন করা (`class`/`note`/`practice`/`exam`)\n"
        "🔹 `/report` ➔ মিনিমাল ভিজ্যুয়াল ড্যাশবোর্ড"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- 📚 সিলেবাস রেঞ্জ পার্সিং ইঞ্জিন ---
def parse_lecture_range(lecture_str):
    lecture_str = lecture_str.upper()
    match = re.match(r"L(\d+)-L?(\d+)", lecture_str)
    if match:
        return [f"L{i}" for i in range(int(match.group(1)), int(match.group(2)) + 1)]
    return [lecture_str]

async def add_syllabus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("❌ ফরম্যাট ভুল! এভাবে লেখো: `/add P1 C1 L1-3`")
        return
    sub, ch = context.args[0].upper(), context.args[1].upper()
    lectures = parse_lecture_range(context.args[2])
    
    current_time_str = new_date_str = get_bd_time().strftime("%a %b %d %Y %H:%M:%S GMT+0600")
    for lec in lectures:
        key = f"{sub}_{ch}_{lec}"
        user_syllabus[key] = {"class": "Pending", "note": "Pending", "practice": "Pending", "exam": "Pending", "last_updated": current_time_str}
        save_syllabus_item(key, {"class": "Pending", "note": "Pending", "practice": "Pending", "exam": "Pending"})
        
    await update.message.reply_text(f"✅ সিলেবাসে **{len(lectures)}টি** লেকচার প্রফেশনাল রো-তে যুক্ত করা হয়েছে।")

async def done_syllabus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not context.args or len(context.args) < 4:
        await update.message.reply_text("❌ ফরম্যাট ভুল! এভাবে লেখো: `/done P1 C1 L1 note`")
        return
    sub, ch = context.args[0].upper(), context.args[1].upper()
    lectures = parse_lecture_range(context.args[2])
    task_type = context.args[3].lower()
    
    if task_type not in ["class", "note", "practice", "exam"]: 
        await update.message.reply_text("❌ টাস্ক টাইপ ভুল! শুধু `class`, `note`, `practice`, বা `exam` ব্যবহার করো।")
        return
        
    updated = 0
    current_time_str = get_bd_time().strftime("%a %b %d %Y %H:%M:%S GMT+0600")
    for lec in lectures:
        key = f"{sub}_{ch}_{lec}"
        if key in user_syllabus:
            user_syllabus[key][task_type] = "Done"
            user_syllabus[key]["last_updated"] = current_time_str
            # ডাটাবেজে ওভাররাইট আটকাতে এক্সিস্টিং ডাটা ধরে রেডি করা
            payload_dict = {task_type: "Done"}
            save_syllabus_item(key, payload_dict)
            updated += 1
            
    if updated > 0:
        await update.message.reply_text(f"🎉 **{updated}টি** লেকচারের {task_type.upper()} সফলভাবে আপডেট করা হয়েছে!")
    else:
        await update.message.reply_text("❌ লেকচারটি সিলেবাসে খুঁজে পাওয়া যায়নি। আগে `/add` করো।")

async def view_syllabus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not user_syllabus:
        await update.message.reply_text("📭 সিলেবাস একদম খালি ভাই।")
        return
    
    filter_prefix = "_".join(context.args).upper() if context.args else ""
    total_tasks, completed_tasks, total_lecs, pending_lecs = 0, 0, 0, 0
    
    for item, status in user_syllabus.items():
        if filter_prefix and not item.startswith(filter_prefix): continue
        total_lecs += 1
        lec_pending = False
        for task in ["class", "note", "practice", "exam"]:
            total_tasks += 1
            if status.get(task, "Pending") == "Done": completed_tasks += 1
            else: lec_pending = True
        if lec_pending: pending_lecs += 1

    if total_lecs == 0:
        await update.message.reply_text("❌ এই ফিল্টারে কোনো ডাটা পাওয়া যায়নি।")
        return

    percentage = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    bar = "█" * int(10 * percentage // 100) + "░" * (10 - int(10 * percentage // 100))
    
    report = (
        f"📊 **সিলেবাস প্রোগ্রেস ড্যাশবোর্ড**\n"
        f"📈 Progress: `[{bar}] {percentage}%`\n"
        f"📝 মোট লেকচার: `{total_lecs}` | ⏳ পেন্ডিং: `{pending_lecs}`\n"
        f"────────────────────\n\n"
    )
    
    for item, status in sorted(user_syllabus.items()):
        if filter_prefix and not item.startswith(filter_prefix): continue
        name = item.replace("_", " ∙ ")
        c = "🟢" if status.get("class", "Pending") == "Done" else "🔴"
        n = "🟢" if status.get("note", "Pending") == "Done" else "🔴"
        p = "🟢" if status.get("practice", "Pending") == "Done" else "🔴"
        e = "🟢" if status.get("exam", "Pending") == "Done" else "🔴"
        report += f"• **{name}** ➔ 📺{c} 📝{n} 🎯{p} 🏆{e}\n"
        
    await update.message.reply_text(report, parse_mode="Markdown")

# --- 🚀 ক্লিন ড্যাশবোর্ড স্ট্যাটাস কমান্ড ---
async def handle_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    _, _, _, total, pending, complete = process_ai_insights()
    
    status_msg = (
        f"🚀 **লাইভ স্ট্যাটাস ড্যাশবোর্ড**\n\n"
        f"📊 **সিলেবাস সামারি:**\n"
        f" ├ 📚 মোট লেকচার: `{total}`\n"
        f" ├ ✅ সম্পূর্ণ লেকচার: `{complete}`\n"
        f" └ ⏳ পেন্ডিং লেকচার: `{pending}`\n\n"
        f"🎯 **আজকের নির্দিষ্ট লক্ষ্য:**\n"
        f"`{user_data['daily_target_raw']}`"
    )
    await update.message.reply_text(status_msg, parse_mode="Markdown")

async def handle_plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_data["is_waiting_for_target"] = True
    await update.message.reply_text("📝 **আজকে রাত ১২টার মধ্যে কোন কোন লেকচার ওড়াতে চাও ভাই? ডিটেইলসে টাইপ করো:**")

async def stop_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    current_jobs = context.job_queue.get_jobs_by_name("hourly_tracker")
    if not current_jobs:
        await update.message.reply_text("🤷‍♂️ কোনো নোটিফিকেশন লুপ একটিভ নেই ভাই।")
        return
    for job in current_jobs: job.schedule_removal()
    user_data["daily_target_raw"] = "No target set yet."
    save_target_to_sheet("No target set yet.")
    await update.message.reply_text("🛑 **আজকের রিমাইন্ডার ইঞ্জিন অফ করা হলো!** জিতু ভাইয়া তোমাকে ছুটি দিল।")

# --- ⏰ অপ্টিমাইজড রিমাইন্ডার ইঞ্জিন ---
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    if user_data["daily_target_raw"] == "No target set yet.": return 
        
    stats_str, recent_pending, recap_item = process_ai_insights()
    bd_time = get_bd_time().strftime("%I:%M %p")

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents="Give me the hourly push notification.",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=stats_str, daily_target_raw=user_data["daily_target_raw"], recent_pending=recent_pending, recap_item=recap_item),
                temperature=0.75,
            ),
        )
        await context.bot.send_message(chat_id=ALLOWED_CHAT_ID, text=response.text, parse_mode="Markdown")
    except Exception as e: 
        logging.error(f"Hourly error: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_text = update.message.text

    # মডার্ন কীবোর্ড বাটন ইন্টারসেপ্ট লজিক (ক্লিন ও বাগ-ফ্রি চেক)
    if '/report' in user_text: 
        # বাটন থেকে কোনো অতিরিক্ত আর্গুমেন্ট থাকলে তা পার্স করার ব্যবস্থা
        args = user_text.split(" ")[1:]
        context.args = args
        return await view_syllabus(update, context)
    if '/status' in user_text: return await handle_status_command(update, context)
    if '/plan' in user_text: return await handle_plan_command(update, context)
    if '/stop_plan' in user_text: return await stop_plan(update, context)

    # ডাইনামিক ডেইলি প্ল্যান ইনপুট প্রসেসিং
    if user_data["is_waiting_for_target"]:
        user_data["daily_target_raw"] = user_text
        user_data["is_waiting_for_target"] = False
        
        current_jobs = context.job_queue.get_jobs_by_name("hourly_tracker")
        for job in current_jobs: job.schedule_removal()
            
        context.job_queue.run_repeating(hourly_mentor_check, interval=3600, first=3600, name="hourly_tracker")
        save_target_to_sheet(user_text)
        
        stats_str, recent_pending, recap_item = process_ai_insights()
        bd_time = get_bd_time().strftime("%I:%M %p")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Set target: {user_text}",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=stats_str, daily_target_raw=user_data["daily_target_raw"], recent_pending=recent_pending, recap_item=recap_item),
                temperature=0.7,
            ),
        )
        await update.message.reply_text(response.text, parse_mode="Markdown")
        return

    # সাধারণ চ্যাট মেকানিজম উইথ জিতু ভাইয়া
    stats_str, recent_pending, recap_item = process_ai_insights()
    bd_time = get_bd_time().strftime("%I:%M %p")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=stats_str, daily_target_raw=user_data["daily_target_raw"], recent_pending=recent_pending, recap_item=recap_item),
                temperature=0.7,
            ),
        )
        await update.message.reply_text(response.text, parse_mode="Markdown")
    except Exception as e: 
        await update.message.reply_text("নেটওয়ার্ক জ্যাম ব্রো!")

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Elite Spaced-Repetition Bot is running perfectly...")
    app.run_polling()

if __name__ == '__main__':
    main()
