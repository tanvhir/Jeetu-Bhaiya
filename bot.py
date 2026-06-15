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

# Modern State Machine Configuration
user_data = {
    "daily_target_raw": "No target set yet.",
    "current_state": "MAIN_MENU" # STATES: MAIN_MENU, WAITING_FOR_TARGET, WAITING_FOR_ADD, WAITING_FOR_CLASS, WAITING_FOR_NOTE, WAITING_FOR_PRACTICE, WAITING_FOR_EXAM
}
user_syllabus = {}

SYSTEM_PROMPT = """
You are 'Jeetu Bhaiya' (from Kota Factory), an elite, deeply empathetic, yet hardcore and practical personal AI Mentor for a Bangladeshi competitive examinee.
You are not just a bot; you are their real elder brother, their support system, and their toughest critic.

### CRITICAL CONTEXT FROM DATABASE:
- Overall Syllabus Stats: {status_str}
- Today's Target: {daily_target_raw}
- Recently Touched but Unfinished: {recent_pending}
- Spaced Repetition Recap: {recap_item}

### LANGUAGE & TONE RULES:
1. STRICTLY speak in 100% NATURAL, CASUAL, COLLOQUIAL BANGLADESHI BENGALI.
2. Never sound like an AI or robot. Do not use overly formal text unless showing stats.
3. Use words like "আরে ভাই", "শোনো", "পড়তে বসো", "টাইম কিন্তু নাই", "২৫ বছর বয়সে গিয়ে আফসোস করবি", "চা খেয়ে পড়তে বসো", "ফাউল করিস না"।
4. Be deeply encouraging when they feel down, but super strict when they waste time.
"""

def get_bd_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=6)

# --- 🧠 লার্নিং অ্যান্ড স্পেসড রেপিটেশন ইঞ্জিন ---
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
        
        lu_str = status.get("last_updated", "")
        days_diff = 0
        if lu_str:
            try:
                parts = lu_str.split(" ")
                if len(parts) >= 4:
                    date_pure_str = f"{parts[1]} {parts[2]} {parts[3]}"
                    parsed_dt = datetime.datetime.strptime(date_pure_str, "%b %d %Y")
                    days_diff = (now.date() - parsed_dt.date()).days
            except Exception: pass

        if done_count == 4:
            complete_lectures += 1
            if days_diff >= 30: recap_list.append(item.replace("_", " "))
        else:
            pending_lectures += 1
            if done_count > 0 and len(recent_pending_list) < 2:
                missing = [t.upper() for t in ["class", "note", "practice", "exam"] if status.get(t) == "Pending"]
                recent_pending_list.append(f"{item.replace('_', ' ')} (Baki: {', '.join(missing)})")

    stats_str = f"Total: {total_lectures} | Done: {complete_lectures} | Pending: {pending_lectures}"
    recent_str = ", ".join(recent_pending_list) if recent_pending_list else "None."
    recap_str = recap_list[0] if recap_list else "None."
    
    return stats_str, recent_str, recap_str, total_lectures, pending_lectures, complete_lectures

# --- 🌐 Database Connections ---
def save_syllabus_item(l_key, task_dict):
    if not APPS_SCRIPT_URL: return
    try:
        payload = {"chat_id": str(ALLOWED_CHAT_ID), "syllabus_update": True, "lecture_key": l_key}
        payload.update(task_dict)
        requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
    except Exception as e: logging.error(f"Save Syllabus Error: {e}")

def save_target_to_sheet(target_text):
    if not APPS_SCRIPT_URL: return
    try:
        payload = {"chat_id": str(ALLOWED_CHAT_ID), "target_update": True, "target": target_text}
        requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
    except Exception as e: logging.error(f"Save Target Error: {e}")

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
    except Exception as e: logging.error(f"Load Error: {e}")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('', port), SimpleHTTPRequestHandler).serve_forever()

# --- 🎛️ ডাইনামিক স্মার্ট কীবোর্ড লেআউটস ---
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        ['📊 স্ট্যাটাস চেক', '🎯 প্ল্যান সেট করো', '📋 প্রোগ্রেস রিপোর্ট'],
        ['🛠️ সিলেবাস ম্যানেজার', '🛑 /stop_plan']
    ], resize_keyboard=True)

def get_syllabus_keyboard():
    return ReplyKeyboardMarkup([
        ['➕ নতুন লেকচার অ্যাড', '📺 CLASS ডান করো'],
        ['📝 NOTE ডান করো', '🎯 PRACTICE ডান করো'],
        ['🏆 EXAM ডান করো', '🔙 মেইন মেনু']
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_data["current_state"] = "MAIN_MENU"
    welcome_text = (
        "আরে ভাই! আমি তোমার মেন্টর জিতু ভাইয়া। 😎\n\n"
        "সব বাটন এখন ডাইনামিক এবং ১০০% স্মার্ট করা হয়েছে। তোমাকে আর কষ্ট করে কমান্ড লিখতে হবে না। "
        "নিচের মেনু থেকে জাস্ট ক্লিক করে পুরো সিলেবাস কন্ট্রোল করতে পারবে। পড়াশোনায় ফাঁকি দিলে কিন্তু খবর আছে!"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

# --- 📚 সিলেবাস রেঞ্জ পার্সিং ---
def parse_lecture_range(lecture_str):
    lecture_str = lecture_str.upper().strip()
    match = re.match(r"L(\d+)-L?(\d+)", lecture_str)
    if match:
        return [f"L{i}" for i in range(int(match.group(1)), int(match.group(2)) + 1)]
    return [lecture_str]

def extract_tokens(text):
    clean_text = text.upper().replace("/", " ").replace("-", " ").strip()
    return [t for t in clean_text.split(" ") if t]

# --- ⚙️ স্মার্ট কোর ফাংশনস ---
async def process_dynamic_add(update: Update, text: str):
    tokens = extract_tokens(text)
    if len(tokens) < 3:
        await update.message.reply_text("❌ ফরম্যাট বোঝো নাই ভাই! এভাবে লেখো: `P1 C1 L1-3` (বা সাবজেক্ট চ্যাপ্টার লেকচার)")
        return
    sub, ch = tokens[0], tokens[1]
    lectures = parse_lecture_range(tokens[2])
    
    current_time_str = get_bd_time().strftime("%a %b %d %Y %H:%M:%S GMT+0600")
    for lec in lectures:
        key = f"{sub}_{ch}_{lec}"
        user_syllabus[key] = {"class": "Pending", "note": "Pending", "practice": "Pending", "exam": "Pending", "last_updated": current_time_str}
        save_syllabus_item(key, {"class": "Pending", "note": "Pending", "practice": "Pending", "exam": "Pending"})
        
    user_data["current_state"] = "MAIN_MENU"
    await update.message.reply_text(f"✅ সাবাশ! সিলেবাসে {len(lectures)}টি লেকচার যোগ করে নিয়েছি। পড়তে বসে যাও!", reply_markup=get_main_keyboard())

async def process_dynamic_done(update: Update, text: str, task_type: str):
    tokens = extract_tokens(text)
    if len(tokens) < 3:
        await update.message.reply_text(f"❌ কোড ভুল ভাই! কোনটার {task_type.upper()} ডান করলা? এভাবে লেখো: `P1 C1 L1`")
        return
    sub, ch = tokens[0], tokens[1]
    lectures = parse_lecture_range(tokens[2])
    
    updated = 0
    current_time_str = get_bd_time().strftime("%a %b %d %Y %H:%M:%S GMT+0600")
    for lec in lectures:
        key = f"{sub}_{ch}_{lec}"
        if key in user_syllabus:
            user_syllabus[key][task_type] = "Done"
            user_syllabus[key]["last_updated"] = current_time_str
            save_syllabus_item(key, {task_type: "Done"})
            updated += 1
            
    user_data["current_state"] = "MAIN_MENU"
    if updated > 0:
        await update.message.reply_text(f"🎉 ওড়ায় দিছিস ভাই! {updated}টি লেকচারের {task_type.upper()} সফলভাবে ডান।", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("❌ এই লেকচারটা তো সিলেবাসে খুঁজে পাচ্ছি না। আগে অ্যাড করতে হবে ভাই!", reply_markup=get_main_keyboard())

async def view_syllabus_smart(update: Update, filter_arg: str = ""):
    if not user_syllabus:
        await update.message.reply_text("📋 সিলেবাস একদম খালি ভাই। আগে ম্যানেজার থেকে কিছু অ্যাড করো।")
        return
    
    filter_prefix = filter_arg.upper().strip()
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
        await update.message.reply_text("❌ এই ফিল্টারে কোনো ডাটা পাওয়া যায়নি ভাই।")
        return

    percentage = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    bar = "█" * int(10 * percentage // 100) + "░" * (10 - int(10 * percentage // 100))
    
    report = (
        f"📋 **সিলেবাস প্রোগ্রেস রিপোর্ট:**\n"
        f"📊 Progress: `[{bar}] {percentage}%`\n"
        f"📚 মোট লেকচার: `{total_lecs}` | ⏳ বাকি আছে: `{pending_lecs}`\n"
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

async def stop_plan_engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_jobs = context.job_queue.get_jobs_by_name("hourly_tracker")
    for job in current_jobs: job.schedule_removal()
    user_data["daily_target_raw"] = "No target set yet."
    user_data["current_state"] = "MAIN_MENU"
    save_target_to_sheet("No target set yet.")
    await update.message.reply_text("🛑 আজকের রিমাইন্ডার অফ করা হলো ভাই। এখন নিজের দায়িত্বে টেবিলে বসো!", reply_markup=get_main_keyboard())

# --- ⏰ অপ্টিমাইজড রিমাইন্ডার ইঞ্জিন ---
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    if user_data["daily_target_raw"] == "No target set yet.": return 
    stats_str, recent_pending, recap_item = process_ai_insights()
    bd_time = get_bd_time().strftime("%I:%M %p")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents="Give me the hourly push notification based on current progress.",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=stats_str, daily_target_raw=user_data["daily_target_raw"], recent_pending=recent_pending, recap_item=recap_item),
                temperature=0.75,
            ),
        )
        await context.bot.send_message(chat_id=ALLOWED_CHAT_ID, text=response.text, parse_mode="Markdown")
    except Exception as e: logging.error(f"Hourly error: {e}")

# --- 💬 ডাইনামিক কীবোর্ড ও মেসেজ রাউটার ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_text = update.message.text.strip()

    # ১. স্টপ প্ল্যানের জন্য আল্ট্রা-সেফটি রুট
    if 'stop_plan' in user_text or '/stop_plan' in user_text:
        return await stop_plan_engine(update, context)

    # ২. প্রধান মেনু বাটন ম্যাচিং (স্পেস-সেফ ফ্রেন্ডলি রিজেক্স/ইন-মেথড)
    if 'স্ট্যাটাস চেক' in user_text or '/status' in user_text:
        _, _, _, total, pending, complete = process_ai_insights()
        status_msg = (
            f"📝 **বর্তমান অবস্থা:**\n\n"
            f"📊 **সিলেবাস সামারি:**\n"
            f" ├ 📚 মোট লেকচার: `{total}`\n"
            f" ├ ✅ সম্পূর্ণ লেকচার: `{complete}`\n"
            f" └ ⏳ পেন্ডিং লেকচার: `{pending}`\n\n"
            f"🎯 **আজকের ফুল প্ল্যান:**\n"
            f"`{user_data['daily_target_raw']}`"
        )
        return await update.message.reply_text(status_msg, parse_mode="Markdown")

    if 'প্ল্যান সেট করো' in user_text or '/plan' in user_text:
        user_data["current_state"] = "WAITING_FOR_TARGET"
        return await update.message.reply_text("📝 **আজকে রাত ১২টার মধ্যে কোন কোন লেকচার ওড়াতে চাও ভাই? ডিটেইলসে টাইপ করে পাঠাও:**")

    if 'প্রোগ্রেস রিপোর্ট' in user_text or user_text.startswith('/report') or user_text.startswith('/view'):
        parts = user_text.split(" ")
        f_arg = parts[1] if len(parts) > 1 and not parts[0].startswith('📋') else ""
        return await view_syllabus_smart(update, f_arg)

    if 'সিলেবাস ম্যানেজার' in user_text:
        return await update.message.reply_text("🛠️ **সিলেবাস কন্ট্রোল প্যানেল অন করা হয়েছে ভাই:**", reply_markup=get_syllabus_keyboard())

    if 'মেইন মেনু' in user_text:
        user_data["current_state"] = "MAIN_MENU"
        return await update.message.reply_text("🔙 প্রধান মেনুতে ফিরে আসা হয়েছে ভাই।", reply_markup=get_main_keyboard())

    # ৩. সিলেবাস সাব-মেনু সিলেকশনস (স্টেট চেঞ্জার)
    if 'নতুন লেকচার অ্যাড' in user_text:
        user_data["current_state"] = "WAITING_FOR_ADD"
        return await update.message.reply_text("✍️ কোন চ্যাপ্টার অ্যাড করতে চাও ভাই? এভাবে কোড পাঠাও:\n`P1 C1 L1-3` (বা `Math Ch2 L1`)")

    if 'CLASS ডান করো' in user_text:
        user_data["current_state"] = "WAITING_FOR_CLASS"
        return await update.message.reply_text("📺 কোন লেকচারের ক্লাস শেষ করলি ভাই? কোড দে: (e.g. `P1 C1 L1`)")

    if 'NOTE ডান করো' in user_text:
        user_data["current_state"] = "WAITING_FOR_NOTE"
        return await update.message.reply_text("📝 কোন লেকচারের নোট রিভিশন ডান ভাই? কোড দে: (e.g. `P1 C1 L1`)")

    if 'PRACTICE ডান করো' in user_text:
        user_data["current_state"] = "WAITING_FOR_PRACTICE"
        return await update.message.reply_text("🎯 কোন লেকচারের প্র্যাকটিস কোয়েশ্চেন ওড়ালি? কোড দে: (e.g. `P1 C1 L1`)")

    if 'EXAM ডান করো' in user_text:
        user_data["current_state"] = "WAITING_FOR_EXAM"
        return await update.message.reply_text("🏆 কোন লেকচারের এক্সাম ডান করলি ভাই? কোড দে: (e.g. `P1 C1 L1`)")

    # ⚠️ ৪. স্টেট মেশিন ডাটা প্রসেসিং (যদি ইউজার কোনো ডাটা ইনপুট মোডে থাকে)
    state = user_data["current_state"]
    
    if state != "MAIN_MENU":
        if state == "WAITING_FOR_TARGET":
            user_data["daily_target_raw"] = user_text
            user_data["current_state"] = "MAIN_MENU"
            
            current_jobs = context.job_queue.get_jobs_by_name("hourly_tracker")
            for job in current_jobs: job.schedule_removal()
            context.job_queue.run_repeating(hourly_mentor_check, interval=3600, first=3600, name="hourly_tracker")
            save_target_to_sheet(user_text)
            
            stats_str, recent_pending, recap_item = process_ai_insights()
            bd_time = get_bd_time().strftime("%I:%M %p")
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"I have set my target to: {user_text}",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT.format(current_time=bd_time, status_str=stats_str, daily_target_raw=user_data["daily_target_raw"], recent_pending=recent_pending, recap_item=recap_item),
                    temperature=0.7,
                ),
            )
            return await update.message.reply_text(response.text, parse_mode="Markdown", reply_markup=get_main_keyboard())

        if state == "WAITING_FOR_ADD": return await process_dynamic_add(update, user_text)
        if state == "WAITING_FOR_CLASS": return await process_dynamic_done(update, user_text, "class")
        if state == "WAITING_FOR_NOTE": return await process_dynamic_done(update, user_text, "note")
        if state == "WAITING_FOR_PRACTICE": return await process_dynamic_done(update, user_text, "practice")
        if state == "WAITING_FOR_EXAM": return await process_dynamic_done(update, user_text, "exam")

    # 🚀 ৫. একদম ফ্রি এবং ওপেন চ্যাট মেকানিজম উইথ জিতু ভাইয়া (কখনোই লক হবে না)
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
        logging.error(f"Gemini Chat Error: {e}")
        await update.message.reply_text("নেটওয়ার্ক একটু জ্যাম ভাই, আবার বল তো?")

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    load_from_google_sheet() 
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop_plan", stop_plan_engine))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Jeetu Bhaiya Pure Dynamic Core is running live...")
    app.run_polling()

if __name__ == '__main__':
    main()
