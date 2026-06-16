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

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# API Keys & Security
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", 5959341337))

OPENROUTER_MODEL = "openai/gpt-oss-120b:free"

# 🧠 State & Memory
user_data = {
    "daily_target_raw": "No target set yet.",
    "current_state": "NORMAL",
    "chat_history": [],
    "kaizen_goals": "কোনো কাইজেন প্ল্যান এখনো সেট করা হয়নি।"
}
MAX_HISTORY_LENGTH = 12 
user_syllabus = {}

# 📖 চ্যাপ্টার ডিকশনারি (Untouched)
CHAPTER_NAMES = {

    # Physics 1st Paper
    "P1_C1": "ভৌত জগৎ ও পরিমাপ",
    "P1_C2": "ভেক্টর",
    "P1_C3": "গতিবিদ্যা",
    "P1_C4": "নিউটনীয় বলবিদ্যা",
    "P1_C5": "কাজ, শক্তি ও ক্ষমতা",
    "P1_C6": "মহাকর্ষ ও অভিকর্ষ",
    "P1_C7": "পদার্থের গাঠনিক ধর্ম",
    "P1_C8": "পর্যাবৃত্ত গতি",
    "P1_C9": "তরঙ্গ",
    "P1_C10": "আদর্শ গ্যাস ও গ্যাসের গতিতত্ত্ব",

    # Physics 2nd Paper
    "P2_C1": "তাপগতিবিদ্যা",
    "P2_C2": "স্থির তড়িৎ",
    "P2_C3": "চল তড়িৎ",
    "P2_C4": "তড়িৎ প্রবাহের চৌম্বক ক্রিয়া ও চৌম্বকত্ব",
    "P2_C5": "তড়িৎচুম্বকীয় আবেশ ও পরিবর্তী প্রবাহ",
    "P2_C6": "জ্যামিতিক আলোকবিজ্ঞান",
    "P2_C7": "ভৌত আলোকবিজ্ঞান",
    "P2_C8": "আধুনিক পদার্থবিজ্ঞানের সূচনা",

    # Chemistry 1st Paper
    "C1_C1": "ল্যাবরেটরির নিরাপদ ব্যবহার",
    "C1_C2": "গুণগত রসায়ন",
    "C1_C3": "মৌলের পর্যায়বৃত্ত ধর্ম ও রাসায়নিক বন্ধন",
    "C1_C4": "রাসায়নিক পরিবর্তন",
    "C1_C5": "কর্মমুখী রসায়ন",

    # Chemistry 2nd Paper
    "C2_C1": "পরিবেশ রসায়ন",
    "C2_C2": "জৈব রসায়ন",
    "C2_C3": "পরিমাণগত রসায়ন",
    "C2_C4": "তড়িৎ রসায়ন",
    "C2_C5": "অর্থনৈতিক রসায়ন",

    # Mathematics 1st Paper
    "M1_C1": "ম্যাট্রিক্স ও নির্ণায়ক",
    "M1_C2": "সরলরেখা",
    "M1_C3": "বৃত্ত",
    "M1_C4": "বিন্যাস ও সমাবেশ",
    "M1_C5": "ত্রিকোণমিতিক অনুপাত",
    "M1_C6": "সংযুক্ত কোণের ত্রিকোণমিতিক অনুপাত",
    "M1_C7": "ফাংশন ও ফাংশনের লেখচিত্র",
    "M1_C8": "অন্তর্বর্তী ও বিপরীত ত্রিকোণমিতিক ফাংশন",
    "M1_C9": "অন্তরীকরণ",
    "M1_C10": "যোগজীকরণ",


    # Mathematics 2nd Paper
    "M2_C1": "বাস্তব সংখ্যা ও অসমতা",
    "M2_C2": "বহুপদী ও বহুপদী সমীকরণ",
    "M2_C3": "জটিল সংখ্যা",
    "M2_C4": "দ্বিপদী বিস্তৃতি",
    "M2_C5": "কণিক",
    "M2_C6": "স্থিতিবিদ্যা",
    "M2_C7": "সমতলে বস্তুকণার গতি",
    "M2_C8": "সম্ভাবনা",
    "M2_C9": "পরিসংখ্যান",

    # Biology 1st Paper
    "B1_C1": "কোষ ও এর গঠন",
    "B1_C2": "কোষ বিভাজন",
    "B1_C3": "কোষ রসায়ন",
    "B1_C4": "অণুজীব",
    "B1_C5": "শৈবাল ও ছত্রাক",
    "B1_C6": "ব্রায়োফাইটা ও টেরিডোফাইটা",
    "B1_C7": "নগ্নবীজী ও আবৃতবীজী উদ্ভিদ",
    "B1_C8": "টিস্যু ও টিস্যুতন্ত্র",
    "B1_C9": "উদ্ভিদ শারীরতত্ত্ব",
    "B1_C10": "উদ্ভিদ প্রজনন",
    "B1_C11": "জীবপ্রযুক্তি",

    # Biology 2nd Paper
    "B2_C1": "প্রাণীর বিভিন্নতা ও শ্রেণিবিন্যাস",
    "B2_C2": "প্রাণীর পরিচিতি",
    "B2_C3": "পরিপাক ও শোষণ",
    "B2_C4": "রক্ত ও সঞ্চালন",
    "B2_C5": "শ্বাসক্রিয়া ও শ্বসন",
    "B2_C6": "বর্জ্য ও নিষ্কাশন",
    "B2_C7": "চলন ও অঙ্গচালনা",
    "B2_C8": "সমন্বয় ও নিয়ন্ত্রণ",
    "B2_C9": "মানব জীবনের ধারাবাহিকতা",
    "B2_C10": "মানবদেহের প্রতিরক্ষা",
    "B2_C11": "জিনতত্ত্ব ও বিবর্তন",
    "B2_C12": "প্রাণীর আচরণ",
    "B2_C13": "জীবের পরিবেশ, বিস্তার ও সংরক্ষণ"

}

def get_friendly_name(lecture_key):
    parts = lecture_key.split("_")
    if len(parts) >= 3:
        sub_ch = f"{parts[0]}_{parts[1]}"
        lec = parts[2].replace("L", "লেকচার ")
        chap_name = CHAPTER_NAMES.get(sub_ch, f"{parts[0]} {parts[1]}")
        return f"{chap_name} - {lec}"
    return lecture_key

# 🚀 SYSTEM PROMPT (UPGRADED WITH KAIZEN LOGIC)
SYSTEM_PROMPT = """
You are 'Jeetu Bhaiya', an elite, deeply empathetic, hardcore, and practical personal AI Mentor for a Bangladeshi examinee.

### CORE PERSONA & RULES:
- STRICTLY speak in NATURAL, CASUAL BANGLADESHI BENGALI (e.g., তুই/তুমি, ভাই, শোন, প্যারা নাই).
- Give "Tough Love": Scold if they slack, but SHOW EMPATHY if they are tired or trying.
- NEVER be a robotic alarm clock. Be unpredictable and human.

### CODE DICTIONARY:
- Short codes: "c2 c1 l1" means Chemistry 2nd Paper, Chapter 1, Lecture 1.

### 🧠 KAIZEN (LIFE & HABIT) ENGINE:
- The user's current Custom Habit/Life Plan: {kaizen_goals}
- If the user discusses a NEW life goal, habit, or routine with you (e.g., sleeping time, namaz, taking a break) and you agree on a plan, you MUST append this secret tag at the VERY END of your message:
<KAIZEN_UPDATE>Write the summarized plan here in Bengali</KAIZEN_UPDATE>
- ONLY use this tag if the lifestyle/habit plan is updated or changed.

### CONTEXT:
- Current Bangladesh Time: {current_time}
- Backlog Status: {status_str}
- Today's Study Target: {daily_target_raw}

### INSTRUCTION FOR THIS MESSAGE:
{context_reason}
"""

def get_bd_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=6)

# --- 🌐 Apps Script Database Sync ---
def save_memory_to_sheet():
    """Background task to save chat history and kaizen goals"""
    if not APPS_SCRIPT_URL: return
    try:
        payload = {
            "chat_id": str(ALLOWED_CHAT_ID),
            "memory_update": True,
            "chat_history": user_data["chat_history"],
            "kaizen_goals": user_data["kaizen_goals"]
        }
        requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Memory Save Error: {e}")

def save_target_to_sheet():
    if not APPS_SCRIPT_URL: return
    try:
        requests.post(APPS_SCRIPT_URL, json={"chat_id": str(ALLOWED_CHAT_ID), "target_update": True, "target": user_data["daily_target_raw"]}, timeout=10)
    except Exception: pass

def save_single_lecture_to_sheet(lecture_key):
    if not APPS_SCRIPT_URL: return
    try:
        s = user_syllabus.get(lecture_key, {})
        payload = {"chat_id": str(ALLOWED_CHAT_ID), "syllabus_update": True, "lecture_key": lecture_key, "class": s.get("class", "Pending"), "note": s.get("note", "Pending"), "practice": s.get("practice", "Pending"), "exam": s.get("exam", "Pending")}
        requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
    except Exception: pass

def load_from_google_sheet():
    global user_data, user_syllabus
    if not APPS_SCRIPT_URL: return
    try:
        res = requests.get(f"{APPS_SCRIPT_URL}?chat_id={ALLOWED_CHAT_ID}", timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("found"):
                user_data["daily_target_raw"] = data.get("target", "No target set yet.")
                user_data["chat_history"] = data.get("chat_history", [])
                user_data["kaizen_goals"] = data.get("kaizen_goals", "কোনো কাইজেন প্ল্যান সেট করা হয়নি।")
                
                new_syllabus = {}
                for key, st in data.get("syllabus", {}).items():
                    new_syllabus[key] = {"class": st.get("class", "Pending"), "note": st.get("note", "Pending"), "practice": st.get("practice", "Pending"), "exam": st.get("exam", "Pending")}
                user_syllabus = new_syllabus
                logging.info("✅ Database & Memory loaded successfully!")
    except Exception as e:
        logging.error(f"Load Error: {e}")

# --- 🌐 OpenRouter Core with Kaizen Interceptor ---
def generate_openrouter_chat(system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
    if not OPENROUTER_API_KEY: return "OpenRouter API Key Missing!"

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(user_data["chat_history"])
    messages.append({"role": "user", "content": user_message})

    payload = {"model": OPENROUTER_MODEL, "messages": messages, "temperature": temperature}
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}, json=payload, timeout=25)
        if response.status_code == 200:
            bot_reply = response.json()["choices"][0]["message"]["content"]
            
            # 🔥 AI Kaizen Interceptor (Detects and extracts the secret tag)
            match = re.search(r"<KAIZEN_UPDATE>(.*?)</KAIZEN_UPDATE>", bot_reply, re.IGNORECASE | re.DOTALL)
            if match:
                user_data["kaizen_goals"] = match.group(1).strip()
                # Remove tag so user doesn't see it
                bot_reply = re.sub(r"<KAIZEN_UPDATE>.*?</KAIZEN_UPDATE>", "", bot_reply, flags=re.IGNORECASE | re.DOTALL).strip()
                logging.info(f"🎯 KAIZEN PLAN UPDATED: {user_data['kaizen_goals']}")

            # Update Memory
            user_data["chat_history"].append({"role": "user", "content": user_message})
            user_data["chat_history"].append({"role": "assistant", "content": bot_reply})
            if len(user_data["chat_history"]) > MAX_HISTORY_LENGTH:
                user_data["chat_history"] = user_data["chat_history"][-MAX_HISTORY_LENGTH:]
            
            # Async save memory to prevent delay
            threading.Thread(target=save_memory_to_sheet, daemon=True).start()
            return bot_reply
    except Exception as e:
        logging.error(f"API Error: {e}")
        return "নেটওয়ার্ক ড্রপ খাইছে ভাই! আবার ট্রাই কর।"

# --- 📊 Analytics (Untouched) ---
def calculate_backlog_metrics():
    total = 0; sub_counts = {"P": 0, "C": 0, "B": 0, "M": 0}
    for item, status in user_syllabus.items():
        if any(status.get(t, "Pending") == "Pending" for t in ["class", "note", "practice", "exam"]):
            total += 1
            sp = item.split("_")[0].upper()[0]
            if sp in sub_counts: sub_counts[sp] += 1
    return total, sub_counts

async def get_status_str():
    total, sub = calculate_backlog_metrics()
    pending = [get_friendly_name(i) for i, s in user_syllabus.items() if any(s.get(t, "Pending") == "Pending" for t in ["class", "note", "practice", "exam"])]
    return f"বাকি ব্যাকলগ: {total} | P: {sub['P']}, C: {sub['C']}, B: {sub['B']}, M: {sub['M']}\nPending Chapters: [{', '.join(pending) if pending else 'Clear!'}]"

def run_dummy_server():
    HTTPServer(('', int(os.environ.get("PORT", 8080))), SimpleHTTPRequestHandler).serve_forever()

def get_main_keyboard():
    return ReplyKeyboardMarkup([['Check Status', 'Set Target', 'Stop Reminders', 'Syllabus Report'], ['Manage Syllabus']], resize_keyboard=True)

def get_syllabus_keyboard():
    return ReplyKeyboardMarkup([['Add New Lecture', 'Mark Class Done'], ['Mark Note Done', 'Mark Practice Done'], ['Mark Exam Done'], ['Back to Main Menu']], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_data["current_state"] = "NORMAL"
    await update.message.reply_text("👋 **আসসালামু আলাইকুম! আমি তোমার মেন্টর 'Jeetu Bhaiya'**\nKaizen Engine Loaded!", reply_markup=get_main_keyboard())

def extract_lecture_details(text):
    parts = text.strip().split()
    if len(parts) < 3: return None, None, None
    ch = parts[1].upper()
    if not ch.startswith("CH") and ch[0].isdigit(): ch = f"CH{ch}"
    match = re.match(r"L(\d+)-L?(\d+)", parts[2].upper())
    lecs = [f"L{i}" for i in range(int(match.group(1)), int(match.group(2)) + 1)] if match else [parts[2].upper()]
    return parts[0].upper(), ch, lecs

async def view_syllabus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not user_syllabus: return await update.message.reply_text("📭 সিলেবাস এখনো খালি ভাই!")
    total = sum(1 for s in user_syllabus.values() for t in ["class", "note", "practice", "exam"])
    done = sum(1 for s in user_syllabus.values() for t in ["class", "note", "practice", "exam"] if s.get(t) == "Done")
    perc = int((done / total) * 100) if total > 0 else 0
    rep = f"📚 **সিলেবাস রিপোর্ট:**\n📈 Progress: `[{'█'*(perc//10)}{'░'*(10-(perc//10))}] {perc}%`\n────────────────\n"
    for i, s in sorted(user_syllabus.items()):
        rep += f"• **{get_friendly_name(i)}** ➔ 📺{'🟢' if s.get('class')=='Done' else '🔴'} 📝{'🟢' if s.get('note')=='Done' else '🔴'} 🎯{'🟢' if s.get('practice')=='Done' else '🔴'} 🏆{'🟢' if s.get('exam')=='Done' else '🔴'}\n"
    await update.message.reply_text(rep, parse_mode="Markdown")

async def stop_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    for job in context.job_queue.get_jobs_by_name("hourly_tracker"): job.schedule_removal()
    user_data["daily_target_raw"] = "No target set yet."
    user_data["current_state"] = "NORMAL"
    save_target_to_sheet()
    await update.message.reply_text("🛑 **রিমাইন্ডার অফ!**", reply_markup=get_main_keyboard())

# --- ⏰ Hourly Mentor Check (Now Kaizen-Aware) ---
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    if user_data["daily_target_raw"] == "No target set yet.": return
    sys_prompt = SYSTEM_PROMPT.format(
        current_time=get_bd_time().strftime("%I:%M %p"), status_str=await get_status_str(),
        daily_target_raw=user_data["daily_target_raw"], kaizen_goals=user_data["kaizen_goals"],
        context_reason="Automated hourly check. Remind them based on their study targets AND their Kaizen/Life goals. Keep it SHORT (1-3 lines max). Use friendly chapter names."
    )
    try:
        response_text = generate_openrouter_chat(sys_prompt, "[SYSTEM: HOURLY REMINDER TRIGGERED]", temperature=0.8)
        await context.bot.send_message(chat_id=ALLOWED_CHAT_ID, text=response_text, parse_mode="Markdown")
    except Exception as e: logging.error(f"Hourly error: {e}")

async def test_hourly_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    await update.message.reply_text("⏳ ১০ সেকেন্ডের ডেমো রিয়েলিটি চেক আসছে...")
    context.job_queue.run_once(hourly_mentor_check, 10)

# --- 💬 Message Router ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    text = update.message.text.strip()
    state = user_data["current_state"]

    if text == 'Check Status': return await update.message.reply_text(await get_status_str())
    elif text == 'Set Target': user_data["current_state"] = "WAITING_FOR_TARGET"; return await update.message.reply_text("📝 **আজকের টার্গেট?**")
    elif text == 'Syllabus Report': return await view_syllabus(update, context)
    elif text == 'Stop Reminders': return await stop_plan(update, context)
    elif text == 'Manage Syllabus': user_data["current_state"] = "NORMAL"; return await update.message.reply_text("📚 **বাটন চাপো:**", reply_markup=get_syllabus_keyboard())
    elif text == 'Back to Main Menu': user_data["current_state"] = "NORMAL"; return await update.message.reply_text("🔙 প্রধান মেনু", reply_markup=get_main_keyboard())
    elif text in ['Add New Lecture', 'Mark Class Done', 'Mark Note Done', 'Mark Practice Done', 'Mark Exam Done']:
        s_map = {"Add": "WAITING_FOR_ADD", "Class": "WAITING_FOR_CLASS", "Note": "WAITING_FOR_NOTE", "Practice": "WAITING_FOR_PRACTICE", "Exam": "WAITING_FOR_EXAM"}
        user_data["current_state"] = s_map[next(k for k in s_map if k in text)]
        return await update.message.reply_text(f"কোড দাও ভাই (e.g. p1 c2 l1)")

    if state == "WAITING_FOR_TARGET":
        user_data["daily_target_raw"] = text
        user_data["current_state"] = "NORMAL"
        save_target_to_sheet()
        for job in context.job_queue.get_jobs_by_name("hourly_tracker"): job.schedule_removal()
        context.job_queue.run_repeating(hourly_mentor_check, interval=3600, first=3600, name="hourly_tracker")
        sys_prompt = SYSTEM_PROMPT.format(current_time=get_bd_time().strftime("%I:%M %p"), status_str=await get_status_str(), daily_target_raw=text, kaizen_goals=user_data["kaizen_goals"], context_reason="User set target. Acknowledge and motivate.")
        return await update.message.reply_text(generate_openrouter_chat(sys_prompt, f"Set target: {text}", 0.7), parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif state == "WAITING_FOR_ADD":
        sub, ch, lecs = extract_lecture_details(text)
        if not sub: return await update.message.reply_text("❌ ফরম্যাট ভুল!")
        added = []
        for lec in lecs:
            key = f"{sub}_{ch}_{lec}"
            if key not in user_syllabus:
                user_syllabus[key] = {"class": "Pending", "note": "Pending", "practice": "Pending", "exam": "Pending"}
                save_single_lecture_to_sheet(key); added.append(get_friendly_name(key))
        user_data["current_state"] = "NORMAL"
        return await update.message.reply_text(f"✅ যোগ করা হয়েছে!\n" + "\n".join([f"📎 {n}" for n in added]) if added else "⚠ অলরেডি আছে!", reply_markup=get_main_keyboard())

    elif state.startswith("WAITING_FOR_"):
        sub, ch, lecs = extract_lecture_details(text)
        if not sub: return await update.message.reply_text("❌ ফরম্যাট ভুল!")
        task = state.split("_")[-1].lower(); updated = 0; last = ""
        for lec in lecs:
            key = f"{sub}_{ch}_{lec}"
            if key in user_syllabus:
                user_syllabus[key][task] = "Done"; save_single_lecture_to_sheet(key); updated += 1; last = get_friendly_name(key)
        user_data["current_state"] = "NORMAL"
        msg = f"🎉 ওড়াধুড়া! **{last}** সহ {updated}টি লেকচারের **{task.upper()}** ডান!" if updated > 0 else "❌ আগে Add New Lecture করো।"
        return await update.message.reply_text(msg, reply_markup=get_main_keyboard())

    # --- Normal Chat (Contextual Kaizen Auto-Triggered Here) ---
    sys_prompt = SYSTEM_PROMPT.format(
        current_time=get_bd_time().strftime("%I:%M %p"), status_str=await get_status_str(),
        daily_target_raw=user_data["daily_target_raw"], kaizen_goals=user_data["kaizen_goals"],
        context_reason="Respond naturally. Use Real Chapter Names. Guide them based on study and life goals."
    )
    await update.message.reply_text(generate_openrouter_chat(sys_prompt, text, 0.7), parse_mode="Markdown")

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    load_from_google_sheet()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    for cmd, func in [("start", start), ("status", start), ("report", view_syllabus), ("stop_plan", stop_plan), ("test_remind", test_hourly_command)]: app.add_handler(CommandHandler(cmd, func))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Jeetu Bhaiya AI V2 (Kaizen + Memory) is Running!")
    app.run_polling()

if __name__ == '__main__': main()
