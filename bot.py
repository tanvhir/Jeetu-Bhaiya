import os
import re
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_SCRIPT_URL = os.getenv("GOOGLE_SCRIPT_URL")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")

# Memory Cache for One-Time States and Data
USER_STATES = {} # Tracks state: 'NORMAL', 'WAITING_TARGET_SET', 'WAITING_TARGET_UPDATE', 'WAITING_KAIZEN_SET', 'WAITING_KAIZEN_UPDATE'
USER_DATA_CACHE = {} 

# --- Keyboards ---
MAIN_MENU_KEYBOARD = [
    ['📊 Check Status', '🎯 Set Target', '📝 Update Target'],
    ['🧠 Manage Kaizen', '🔄 Update Kaizen', '📁 Syllabus Report']
]
reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)

# --- Google Sheet Integrations ---
def sync_with_sheet(action_data):
    try:
        response = requests.post(GOOGLE_SCRIPT_URL, json=action_data, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Sheet integration error: {e}")
        return {"status": "error", "message": str(e)}

def fetch_live_status(chat_id):
    res = sync_with_sheet({"action": "get_user_data", "chat_id": chat_id})
    if res.get("status") == "success":
        return res.get("target"), res.get("target_status")
    return "No target set yet.", "None"

# --- OpenRouter AI Handler ---
def ask_jeetu_bhaiya(system_prompt, user_message, chat_history=[]):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    messages = [{"role": "system", "content": system_prompt}]
    for h in chat_history[-10:]: # Lock history to last 5 pairs max
        messages.append(h)
    messages.append({"role": "user", "content": user_message})
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages
    }
    
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=15)
        return res.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"জিতু ভাইয়া একটু ব্যস্ত রে ভাই। (Error: {e})"

# --- Core Prompts ---
BASE_SYSTEM_PROMPT = """
তুমি হলে 'জিতু ভাইয়া' (Jeetu Bhaiya)—একজন কড়া, বাস্তববাদী কিন্তু অত্যন্ত দরদী মেন্টর। 
ইউজার তানভীর একজন 'সেকেন্ড টাইমার' বুয়েট/মেডিকেল এডমিশন পরীক্ষার্থী (পরীক্ষা ডিসেম্বর ২০২৬)। 
তার ৩০টিরও বেশি ব্যাকলগ আছে। তাকে বেশি চাপ না দিয়ে প্রতিদিন ১-২টি করে ব্যাকলগ কভার করাবে। 
সবসময় চ্যাট বাংলায় হবে, একদম রিয়ালিস্টিক ও ডায়নামিক মেন্টরিং টোন। খামখেয়ালি দেখলে কড়া বকা দেবে।
"""

# --- Bot Commands/Actions ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    USER_STATES[chat_id] = 'NORMAL'
    welcome_text = "কিরে তানভীর! টেবিলে বসছিস? আমি তোর জিতু ভাইয়া। এখন থেকে তোর এডমিশন জার্নি আমি ট্র্যাক করব। নিচের বাটনগুলো ব্যবহার কর।"
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def handle_buttons_and_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    current_state = USER_STATES.get(chat_id, 'NORMAL')
    
    # Initialize cache row if empty
    if chat_id not in USER_DATA_CACHE:
        USER_DATA_CACHE[chat_id] = {"kaizen_goal": "রাত ১২টার মধ্যে ঘুমানো", "history": []}
    
    # Fetch latest target data from sheet
    live_target, live_status = fetch_live_status(chat_id)
    
    # ------------------ GATEWAY BUTTONS CLICKED ------------------
    if text == '📊 Check Status':
        USER_STATES[chat_id] = 'NORMAL'
        dashboard = (
            f"Status Dashboard\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 আজকের টার্গেটঃ {live_target} [অবস্থা: {live_status}]\n"
            f"🧠 কাইজেন গোলঃ {USER_DATA_CACHE[chat_id]['kaizen_goal']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"জিতু ভাইয়া তোর প্রোগ্রেস মনিটর করছে। ফাঁকি দিলেই কড়া অ্যাকশন!"
        )
        await update.message.reply_text(dashboard, reply_markup=reply_markup)
        return

    elif text == '🎯 Set Target':
        USER_STATES[chat_id] = 'WAITING_TARGET_SET'
        await update.message.reply_text("আজকের মিশন বা টার্গেটটা লিখে দে শুনি? (চ্যাপ্টারের নাম বল)", reply_markup=reply_markup)
        return

    elif text == '📝 Update Target':
        USER_STATES[chat_id] = 'WAITING_TARGET_UPDATE'
        await update.message.reply_text(f"তোর কারেন্ট টার্গেট: '{live_target}'। এটা কি শেষ করেছিস নাকি অর্ধেক হয়েছে? ক্যাজুয়ালি আমাকে বল।", reply_markup=reply_markup)
        return

    elif text == '🧠 Manage Kaizen':
        USER_STATES[chat_id] = 'WAITING_KAIZEN_SET'
        await update.message.reply_text("তোর নতুন কাইজেন গোল লাইফস্টাইল অভ্যাসটা কী সেট করতে চাস বল? (যেমন: সকাল ৬টায় উঠবো)", reply_markup=reply_markup)
        return

    elif text == '🔄 Update Kaizen':
        USER_STATES[chat_id] = 'WAITING_KAIZEN_UPDATE'
        await update.message.reply_text(f"তোর কাইজেন গোল ছিল: '{USER_DATA_CACHE[chat_id]['kaizen_goal']}'। কালকের আপডেটের অবস্থা বল, সফল নাকি ব্যর্থ? কী হয়েছিল ডিটেইলসে বল।", reply_markup=reply_markup)
        return

    # ------------------ PROCESS INPUT BASED ON STATES ------------------
    
    # STATE: SETTING TARGET
    if current_state == 'WAITING_TARGET_SET':
        sync_with_sheet({"action": "set_target", "chat_id": chat_id, "target_name": text})
        USER_STATES[chat_id] = 'NORMAL' # Immediately reset state to Normal
        prompt = f"{BASE_SYSTEM_PROMPT}\nইউজার এইমাত্র একটি নতুন ডেইলি টার্গেট সেট করল: {text}। তাকে উৎসাহ দাও কিন্তু ওভার-প্রমিজ করতে না করো।"
        response = ask_jeetu_bhaiya(prompt, text, USER_DATA_CACHE[chat_id]["history"])
        USER_DATA_CACHE[chat_id]["history"].append({"role": "user", "content": text})
        USER_DATA_CACHE[chat_id]["history"].append({"role": "assistant", "content": response})
        await update.message.reply_text(response, reply_markup=reply_markup)
        return

    # STATE: UPDATING TARGET (AI POWERED PARSING)
    elif current_state == 'WAITING_TARGET_UPDATE':
        USER_STATES[chat_id] = 'NORMAL' # Immediately reset state to Normal
        parsing_prompt = (
            f"{BASE_SYSTEM_PROMPT}\nইউজার তার টার্গেট '{live_target}' এর আপডেট দিচ্ছে। "
            f"তোর প্রধান কাজ তার কথা বিশ্লেষণ করে রেসপন্সের শেষে অবশ্যই নিচের যেকোনো একটি ট্যাগ প্রিন্ট করা:\n"
            f"যদি সে বলে শেষ বা সফল হয়েছে: <TARGET_PARSE>Done</TARGET_PARSE>\n"
            f"যদি সে বলে আংশিক বা অর্ধেক হয়েছে: <TARGET_PARSE>Half Done</TARGET_PARSE>\n"
            f"যদি সে করতে না পারে বা বাতিল করতে চায়: <TARGET_PARSE>Failed</TARGET_PARSE>"
        )
        response = ask_jeetu_bhaiya(parsing_prompt, text, USER_DATA_CACHE[chat_id]["history"])
        
        # Extracted tag and push to sheet
        match = re.search(r'<TARGET_PARSE>(.*?)</TARGET_PARSE>', response)
        parsed_status = match.group(1) if match else "Pending"
        clean_response = re.sub(r'<TARGET_PARSE>.*?</TARGET_PARSE>', '', response).strip()
        
        sync_with_sheet({"action": "update_target", "chat_id": chat_id, "status": parsed_status})
        
        USER_DATA_CACHE[chat_id]["history"].append({"role": "user", "content": text})
        USER_DATA_CACHE[chat_id]["history"].append({"role": "assistant", "content": clean_response})
        await update.message.reply_text(clean_response, reply_markup=reply_markup)
        return

    # STATE: MANAGING KAIZEN GOAL
    elif current_state == 'WAITING_KAIZEN_SET':
        USER_STATES[chat_id] = 'NORMAL' # Immediately reset state to Normal
        USER_DATA_CACHE[chat_id]["kaizen_goal"] = text
        prompt = f"{BASE_SYSTEM_PROMPT}\nইউজার একটি নতুন কাইজেন লাইফস্টাইল গোল সেট করেছে: '{text}'। মেন্টর হিসেবে তাকে প্র্যাক্টিক্যাল চ্যালেঞ্জ দাও।"
        response = ask_jeetu_bhaiya(prompt, text, USER_DATA_CACHE[chat_id]["history"])
        USER_DATA_CACHE[chat_id]["history"].append({"role": "user", "content": text})
        USER_DATA_CACHE[chat_id]["history"].append({"role": "assistant", "content": response})
        await update.message.reply_text(response, reply_markup=reply_markup)
        return

    # STATE: LOGGING DAILY KAIZEN STATUS (AI POWERED PARSING)
    elif current_state == 'WAITING_KAIZEN_UPDATE':
        USER_STATES[chat_id] = 'NORMAL' # Immediately reset state to Normal
        current_goal = USER_DATA_CACHE[chat_id]["kaizen_goal"]
        parsing_prompt = (
            f"{BASE_SYSTEM_PROMPT}\nইউজার তার কাইজেন গোল '{current_goal}' এর বাস্তবায়ন রিপোর্ট দিচ্ছে। "
            f"তোর প্রধান কাজ তার কথা বিশ্লেষণ করে রেসপন্সের শেষে অবশ্যই নিচের নিয়মে ট্যাগ প্রিন্ট করা:\n"
            f"ফরম্যাট: <KAIZEN_PARSE>STATUS|সংক্ষিপ্ত নোট</KAIZEN_PARSE>\n"
            f"STATUS হবে শুধুমাত্র SUCCESS অথবা FAILURE। উদাহরণ: <KAIZEN_PARSE>SUCCESS|১২টায় ঘুমিয়েছে</KAIZEN_PARSE>"
        )
        response = ask_jeetu_bhaiya(parsing_prompt, text, USER_DATA_CACHE[chat_id]["history"])
        
        match = re.search(r'<KAIZEN_PARSE>(.*?)\|(.*?)</KAIZEN_PARSE>', response)
        if match:
            k_status = match.group(1)
            k_note = match.group(2)
            sync_with_sheet({
                "action": "log_kaizen",
                "chat_id": chat_id,
                "goal_name": current_goal,
                "status": k_status,
                "log_text": k_note
            })
        
        clean_response = re.sub(r'<KAIZEN_PARSE>.*?</KAIZEN_PARSE>', '', response).strip()
        USER_DATA_CACHE[chat_id]["history"].append({"role": "user", "content": text})
        USER_DATA_CACHE[chat_id]["history"].append({"role": "assistant", "content": clean_response})
        await update.message.reply_text(clean_response, reply_markup=reply_markup)
        return

    # ------------------ STATE: NORMAL CHAT MODE ------------------
    # এই মোডে ইউজার হাজারটা কথা বললেও ব্যাকএন্ড শিটের বা লগের কোনো ডেটা এডিট হবে না!
    else:
        prompt = (
            f"{BASE_SYSTEM_PROMPT}\n"
            f"কারেন্ট টাইম: {datetime.now().strftime('%I:%M %p')}\n"
            f"ইউজারের বর্তমান সেট করা অফিশিয়াল টার্গেট: '{live_target}' [অবস্থা: {live_status}].\n"
            f"ইউজার জাস্ট ক্যাজুয়াল চ্যাট করছে। কথা বলো কিন্তু কোনো কাইজেন লগ বা অফিশিয়াল টার্গেট এডিট করার সিক্রেট ট্যাগ আউটপুট করবে না।"
        )
        response = ask_jeetu_bhaiya(prompt, text, USER_DATA_CACHE[chat_id]["history"])
        USER_DATA_CACHE[chat_id]["history"].append({"role": "user", "content": text})
        USER_DATA_CACHE[chat_id]["history"].append({"role": "assistant", "content": response})
        await update.message.reply_text(response, reply_markup=reply_markup)

# --- Hourly Smarter Reminder Engine ---
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    current_hour = datetime.now().hour
    # রাত ১২টা থেকে সকাল ৬টা পর্যন্ত রিমাইন্ডার বন্ধ থাকবে (স্লিপ মোড ফিল্টার)
    if current_hour >= 0 and current_hour < 6:
        return
        
    for chat_id in USER_STATES.keys():
        live_target, live_status = fetch_live_status(chat_id)
        # টার্গেট যদি অলরেডি শেষ (Done) হয়ে থাকে, তবে রিমাইন্ডার বিরক্ত করবে না
        if live_status.lower() in ["done", "completed"]:
            continue
            
        reminder_prompt = (
            f"{BASE_SYSTEM_PROMPT}\n"
            f"এটি একটি অটোমেটিক ১ ঘণ্টার অ্যালার্ট রিমাইন্ডার। ইউজারের আজকের পেন্ডিং টার্গেট হলো: '{live_target}'। "
            f"তাকে ১ ঘণ্টা পার হওয়ার কড়া ওয়ার্নিং দাও এবং পড়া কতদূর হলো জানতে চাও।"
        )
        response = ask_jeetu_bhaiya(reminder_prompt, "[SYSTEM: RUNNING HOURLY MONITOR CHECK]")
        await context.bot.send_message(chat_id=chat_id, text=response, reply_markup=reply_markup)

# --- Application Launcher ---
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Queue Registration for Hourly Reminders
    if application.job_queue:
        application.job_queue.run_repeating(hourly_mentor_check, interval=3600, first=3600, name="hourly_tracker")
        
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons_and_chat))
    
    logger.info("Jeetu Bhaiya V4 Engine Deployed & Live!")
    application.run_polling()

if __name__ == '__main__':
    main()
