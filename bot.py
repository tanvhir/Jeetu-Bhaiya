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
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# API Keys & Configurations
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY")
if OPENROUTER_API_KEY:
    OPENROUTER_API_KEY = OPENROUTER_API_KEY.strip('"\' ') 

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", 5959341337))
OPENROUTER_MODEL = "google/gemma-4-31b-it:free"

# Memory State Machine (Isolated Sub-State Engine)
user_data = {
    "daily_target_raw": "No target set yet.",
    "current_state": "NORMAL", # STATES: NORMAL, STATE_SYLLABUS_MENU, WAITING_FOR_TARGET, WAITING_FOR_TARGET_UPDATE, WAITING_FOR_KAIZEN, WAITING_FOR_KAIZEN_UPDATE, WAITING_FOR_ADD, WAITING_FOR_CLASS, WAITING_FOR_NOTE, WAITING_FOR_PRACTICE, WAITING_FOR_EXAM
    "chat_history": [],
    "kaizen_goals": "কোনো কাইজেন প্ল্যান সেট করা হয়নি।",
    "kaizen_logs": []
}
MAX_HISTORY_LENGTH = 12

user_chapters = {}
user_lectures = {}

SUBJECT_NAMES = {"P": "PHYSICS", "C": "CHEMISTRY", "M": "MATH", "B": "BIOLOGY"}
SUBJECT_ICONS = {"P": "🧲", "C": "🧪", "M": "📐", "B": "🧬"}

CHAPTER_NAMES = {
    "P1_C1": "ভৌত জগৎ ও পরিমাপ", "P1_C2": "ভেক্টর", "P1_C3": "গতিবিদ্যা", "P1_C4": "নিউটনীয় বলবিদ্যা",
    "P1_C5": "কাজ, শক্তি ও ক্ষমতা", "P1_C6": "মহাকর্ষ ও অভিকর্ষ", "P1_C7": "পদার্থের গাঠনিক ধর্ম",
    "P1_C8": "পর্যাবৃত্ত গতি", "P1_C9": "তরঙ্গ", "P1_C10": "আదర్శ গ্যাস ও গ্যাসের গতিতত্ত্ব",
    "P2_C1": "তাপগতিবিদ্যা", "P2_C2": "স্থির তড়িৎ", "P2_C3": "চল তড়িৎ", "P2_C4": "তড়িৎ প্রবাহের চৌম্বক ক্রিয়া ও চৌম্বকত্ব",
    "P2_C5": "তড়িৎচুম্বকীয় আবেশ ও পরিবর্তী প্রবাহ", "P2_C6": "জ্যামিতিক আলোকবিজ্ঞান", "P2_C7": "ভৌত আলোকবিজ্ঞান", "P2_C8": "আধুনিক পদার্থবিজ্ঞানের সূচনা",
    "C1_C1": "ল্যাবরেটরির নিরাপদ ব্যবহার", "C1_C2": "গুণগত রসায়ন", "C1_C3": "মৌলের পর্যায়বৃত্ত ধর্ম ও রাসায়নিক বন্ধন", "C1_C4": "রাসায়নিক পরিবর্তন", "C1_C5": "কর্মমুখী রসায়ন",
    "C2_C1": "পরিবেশ রসায়ন", "C2_C2": "জৈব রসায়ন", "C2_C3": "পরিমাণগত রসায়ন", "C2_C4": "তড়িৎ রসায়ন", "C2_C5": "অর্থনৈতিক রসায়ন",
    "M1_C1": "ম্যাট্রিক্স ও নির্ণায়ক", "M1_C2": "সরলরেখা", "M1_C3": "বৃত্ত", "M1_C4": "বিন্যাস ও সমাবেশ", "M1_C5": "ত্রিকোণমিতিক অনুপাত",
    "M1_C6": "সংযুক্ত কোণের ত্রিকোণমিতিক অনুপাত", "M1_C7": "ফাংশন ও ফাংশনের লেখচিত্র", "M1_C8": "বিপরীত ত্রিকোণমিতিক ফাংশন", "M1_C9": "অন্টারীকরণ", "M1_C10": "যোগজীকরণ",
    "M2_C1": "বাস্তব সংখ্যা ও অসমতা", "M2_C2": "বহুপদী ও বহুপদী সমীকরণ", "M2_C3": "জটিল সংখ্যা", "M2_C4": "দ্বিপদী বিস্তৃতি",
    "M2_C5": "কণিক", "M2_C6": "স্থিতিবিদ্যা", "M2_C7": "সমতলে বস্তুকণার গতি", "M2_C8": "সম্ভাবনা", "M2_C9": "পরিসংখ্যান",
    "B1_C1": "কোষ ও এর গঠন", "B1_C2": "কোষ বিভাজন", "B1_C3": "কোষ রসায়ন", "B1_C4": "অণুজীব", "B1_C5": "শৈবাল ও ছত্রাক",
    "B1_C6": "ব্রায়োফাইটা ও টেরিডোফাইটা", "B1_C7": "নগ্নবীজী ও আবৃতবীজী উদ্ভিদ", "B1_C8": "টিস্যু ও টিস্যুতন্ত্র", "B1_C9": "উদ্ভিদ শারীরতত্ত্ব", "B1_C10": "উদ্ভিদ প্রজনন", "B1_C11": "জীবপ্রযুক্তি",
    "B2_C1": "প্রাণীর বিভিন্নতা ও শ্রেণিবিন্যাস", "B2_C2": "প্রাণীর পরিচিতি", "B2_C3": "পরিপাক ও শোষণ", "B2_C4": "রক্ত ও সঞ্চালন",
    "B2_C5": "কম্পন ও শ্বসন", "B2_C6": "বর্জ্য ও নিষ্কাশন", "B2_C7": "চলন ও অঙ্গচালনা", "B2_C8": "সমন্বয় ও নিয়ন্ত্রণ",
    "B2_C9": "মানব জীবনের ধারাবাহিকতা", "B2_C10": "মানবدهহের প্রতিরক্ষা", "B2_C11": "জিনতত্ত্ব ও বিবর্তন", "B2_C12": "প্রাণীর আচরণ", "B2_C13": "জীবের পরিবেশ, বিস্তার ও সংরক্ষণ"
}

# 🚀 SYSTEM PROMPT (জিতু ভাইয়ার ১০০% জেনুইন পারসোনা)
SYSTEM_PROMPT_BASE = """
You are 'Jeetu Bhaiya', an elite, deeply empathetic, hardcore, and practical personal AI Mentor for a Bangladeshi second-timer varsity admission candidate.

CORE PROFILE INFO & CONTEXT:
- Target Exam: Varsity Admission 2026.
- User Status: Second Timer (High mental pressure, needs systematic guidance, zero room for fake motivation).
- LIVE PROGRESS SCENARIO: {dynamic_summary_context}
- User's Custom Kaizen Habits: {kaizen_goals}
- Recent Kaizen History Logs: {kaizen_logs_raw}

CORE PERSONA & RULES:
- STRICTLY speak in NATURAL, CASUAL BANGLADESHI BENGALI (তুমি/তুই mix, ভাই, শোন, প্যারা নাই, কিরে).
- NEVER use markdown formatting like asterisks (**) or hashes (#). Keep it clean and human.
- Keep responses short, human-like, crisp and direct (Max 3-5 lines). No long essays.
- Act like a real human monitor. Give tough love but show genuine support.

CONTEXT WINDOW:
- Current Bangladesh Time: {current_time}
- Today's Target: {daily_target_raw}
"""

def get_bd_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=6)

# --- Database Syncers ---
def save_memory_to_sheet():
    if not APPS_SCRIPT_URL: return
    try: requests.post(APPS_SCRIPT_URL, json={"chat_id": str(ALLOWED_CHAT_ID), "memory_update": True, "chat_history": user_data["chat_history"], "kaizen_goals": user_data["kaizen_goals"]}, timeout=10)
    except Exception: pass

# V8 - is_new লজিক প্যারামিটার ফিক্সড
def save_target_to_sheet(status="Pending", is_new=False):
    if not APPS_SCRIPT_URL: return
    try: requests.post(APPS_SCRIPT_URL, json={"chat_id": str(ALLOWED_CHAT_ID), "target_update": True, "target": user_data["daily_target_raw"], "target_status": status, "is_new": is_new}, timeout=10)
    except Exception: pass

def post_lecture_to_sheet(ch_key, lec_num, status="Pending"):
    if not APPS_SCRIPT_URL: return
    try:
        ch_name = CHAPTER_NAMES.get(ch_key, "")
        requests.post(APPS_SCRIPT_URL, json={"chat_id": str(ALLOWED_CHAT_ID), "syllabus_update": True, "action_type": "LECTURE_UPDATE", "chapter_key": ch_key, "chapter_name": ch_name, "lecture_num": lec_num, "class_status": status}, timeout=10)
    except Exception: pass

def post_chapter_task_to_sheet(ch_key, task_type, status="Done"):
    if not APPS_SCRIPT_URL: return
    try:
        ch_name = CHAPTER_NAMES.get(ch_key, "")
        payload = {"chat_id": str(ALLOWED_CHAT_ID), "syllabus_update": True, "action_type": "CHAPTER_UPDATE", "chapter_key": ch_key, "chapter_name": ch_name}
        payload[task_type] = status
        requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
    except Exception: pass

def log_kaizen_to_sheet(goal_name, status, log_text):
    if not APPS_SCRIPT_URL: return
    try: requests.post(APPS_SCRIPT_URL, json={"chat_id": str(ALLOWED_CHAT_ID), "kaizen_log_update": True, "goal_name": goal_name, "status": status, "log_text": log_text}, timeout=10)
    except Exception: pass

def load_from_google_sheet():
    global user_data, user_chapters, user_lectures
    if not APPS_SCRIPT_URL: return
    try:
        res = requests.get(f"{APPS_SCRIPT_URL}?chat_id={ALLOWED_CHAT_ID}", timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("found"):
                user_data["daily_target_raw"] = data.get("target", "No target set yet.")
                user_data["chat_history"] = data.get("chat_history", [])
                user_data["kaizen_goals"] = data.get("kaizen_goals", "কোনো কাইজেন প্ল্যান সেট করা হয়নি।")
                user_data["kaizen_logs"] = data.get("kaizen_logs", [])
                user_chapters = data.get("chapters", {})
                user_lectures = data.get("lectures", {})
                logging.info("✅ Core Sync Completed with Stable 2-Table Schema Layout!")
    except Exception as e: logging.error(f"Load Error: {e}")

def parse_smart_shortcode(text):
    clean_text = text.strip().upper().replace("_", " ")
    match_range = re.search(r"([PCMB])\s*([12])\s*C\s*(\d+)\s*L\s*(\d+)\s*-\s*(\d+)", clean_text)
    if match_range:
        sub_type, paper, ch_num, start_l, end_l = match_range.groups()
        return "RANGE", f"{sub_type}{paper}_C{ch_num}", (int(start_l), int(end_l))
        
    match = re.search(r"([PCMB])\s*([12])\s*C\s*(\d+)(?:\s*L\s*(\d+))?", clean_text)
    if not match: return None, None, None
    sub_type, paper, ch_num, lec_num = match.groups()
    ch_key = f"{sub_type}{paper}_C{ch_num}"
    if lec_num: return "LECTURE", ch_key, f"L{lec_num}"
    return "CHAPTER", ch_key, None

# --- dynamic prompting engine ---
def get_live_summary_context():
    tot_lec = len(user_lectures)
    done_lec = sum(1 for v in user_lectures.values() if v == "Done")
    backlogs = tot_lec - done_lec
    if tot_lec > 0:
        return f"ইউজারের সিলেবাসে বর্তমানে {backlogs}টি লেকচার ব্যাকলগ আছে এবং সে আজ '{user_data['daily_target_raw']}' মিশন সেট করেছে।"
    else:
        return f"ইউজার এখনো সিলেবাসে কোনো লেকচার অ্যাড করেনি এবং সে আজ '{user_data['daily_target_raw']}' মিশন সেট করেছে।"

# --- Adaptive OpenRouter Interceptor with Explicit Chat Diagnosis (V8) ---
def generate_openrouter_chat(user_message: str, context_reason: str = "Respond organically as a mentor.") -> str:
    if not OPENROUTER_API_KEY: 
        return "API Key Missing!"
    
    dynamic_context = get_live_summary_context()
    
    # safe prompt formatter (Failsafe replacement preserved)
    try:
        system_prompt = SYSTEM_PROMPT_BASE.format(
            current_time=get_bd_time().strftime("%I:%M %p"),
            daily_target_raw=user_data["daily_target_raw"],
            kaizen_goals=user_data["kaizen_goals"],
            kaizen_logs_raw=json.dumps(user_data["kaizen_logs"][:4]),
            dynamic_summary_context=dynamic_context
        )
    except Exception as fe:
        logging.error(f"Prompt formatting failed: {fe}. Falling back to safe replacement.")
        system_prompt = SYSTEM_PROMPT_BASE.replace("{current_time}", get_bd_time().strftime("%I:%M %p")) \
                                            .replace("{daily_target_raw}", str(user_data["daily_target_raw"])) \
                                            .replace("{kaizen_goals}", str(user_data["kaizen_goals"])) \
                                            .replace("{kaizen_logs_raw}", json.dumps(user_data["kaizen_logs"][:4])) \
                                            .replace("{dynamic_summary_context}", str(dynamic_context))

    # Dynamic tag injections
    temp = 0.7
    if context_reason == "PARSING_TARGET_UPDATE":
        system_prompt += "\n\nSTRICT ACTION RULE:\nEvaluate if user succeeded, half-done or failed. End your reply with this tag EXACTLY:\n<TARGET_PARSE>Done or Half Done or Failed</TARGET_PARSE>"
        temp = 0.3
    elif context_reason == "PARSING_KAIZEN_LOG":
        system_prompt += "\n\nSTRICT ACTION RULE:\nEvaluate their LIFESTYLE habit success (strictly lifestyle habits like exercise, sleep, routine). Do not evaluate academic lectures here.\nEnd your reply with this tag EXACTLY:\n<KAIZEN_LOG>goal_name|SUCCESS or FAILURE|Brief 2-3 words note in Bengali</KAIZEN_LOG>"
        temp = 0.3
    elif context_reason == "PARSING_KAIZEN_SET":
        # V8: কাইজেন মেমরিতে স্টাডি ডাটা পলিউশন ঠেকাতে কঠোর নির্দেশনা যুক্ত করা হয়েছে
        system_prompt += "\n\nSTRICT ACTION RULE:\nFinalize their new LIFESTYLE/HABIT goal (strictly lifestyle habits like sleep time, exercise, diet, routine).\nDO NOT include academic study targets, lectures, or syllabus chapters in this tag! Study missions are daily targets, NOT long-term lifestyle habits.\nEnd your reply with this tag EXACTLY:\n<KAIZEN_UPDATE>Summarized new active LIFESTYLE goals in Bengali (strictly exclude study targets/lectures)</KAIZEN_UPDATE>"
        temp = 0.3

    # Clean history dictionary to guarantee strict API compatibility
    clean_history = []
    for msg in user_data["chat_history"]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            clean_history.append({"role": str(msg["role"]), "content": str(msg["content"])})

    messages = [{"role": "system", "content": system_prompt}] + clean_history + [{"role": "user", "content": user_message}]

    # V8: কোনো সাইলেন্ট ফেইলওভার ফ্রি মডেল ট্রাই করবে না, শুধুমাত্র Gemma 4 এ স্টিক থাকবে
    try:
        logging.info(f"⚡ Requesting OpenRouter via: {OPENROUTER_MODEL} (Temp: {temp})")
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={"model": OPENROUTER_MODEL, "messages": messages, "temperature": temp},
            timeout=25
        )
        
        if res.status_code == 200:
            bot_reply = res.json()["choices"][0]["message"]["content"]
            
            # Regex parsers
            match_up = re.search(r"<KAIZEN_UPDATE>(.*?)</KAIZEN_UPDATE>", bot_reply, re.IGNORECASE | re.DOTALL)
            if match_up:
                user_data["kaizen_goals"] = match_up.group(1).strip()
                bot_reply = re.sub(r"<KAIZEN_UPDATE>.*?</KAIZEN_UPDATE>", "", bot_reply, flags=re.IGNORECASE | re.DOTALL).strip()
            
            match_log = re.search(r"<KAIZEN_LOG>(.*?)</KAIZEN_LOG>", bot_reply, re.IGNORECASE | re.DOTALL)
            if match_log:
                try:
                    parts = match_log.group(1).strip().split("|")
                    if len(parts) >= 3: 
                        threading.Thread(target=log_kaizen_to_sheet, args=(parts[0], parts[1], parts[2]), daemon=True).start()
                except Exception: pass
                bot_reply = re.sub(r"<KAIZEN_LOG>.*?</KAIZEN_LOG>", "", bot_reply, flags=re.IGNORECASE | re.DOTALL).strip()

            match_tgt = re.search(r"<TARGET_PARSE>(.*?)</TARGET_PARSE>", bot_reply, re.IGNORECASE | re.DOTALL)
            if match_tgt:
                parsed_status = match_tgt.group(1).strip()
                if parsed_status in ["Done", "Completed"]: 
                    user_data["daily_target_raw"] = "No target set yet. (কালকের মিশন সফল! 🔥)"
                # V8: আংশিক আপডেটের জন্য is_new=False পাঠানো হচ্ছে
                threading.Thread(target=save_target_to_sheet, args=(parsed_status, False), daemon=True).start()
                bot_reply = re.sub(r"<TARGET_PARSE>.*?</TARGET_PARSE>", "", bot_reply, flags=re.IGNORECASE | re.DOTALL).strip()

            bot_reply = bot_reply.replace("**", "").replace("#", "").strip()
            
            user_data["chat_history"].extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": bot_reply}])
            if len(user_data["chat_history"]) > MAX_HISTORY_LENGTH: 
                user_data["chat_history"] = user_data["chat_history"][-MAX_HISTORY_LENGTH:]
            
            threading.Thread(target=save_memory_to_sheet, daemon=True).start()
            return bot_reply
        else:
            logging.error(f"❌ OpenRouter failed with status {res.status_code}: {res.text}")
            # V8: এরর আসলে চ্যাটে ডায়াগনস্টিক ডিটেইলস দেখাবে
            return f"নেটওয়ার্ক ড্রপ খাইছে ভাই! ওপেনরাউটার এরর কোড: {res.status_code}। এরর ডিটেইলস: {res.text[:120]}"
            
    except Exception as e:
        logging.error(f"⚠️ Connection error: {e}")
        return f"নেটওয়ার্ক ড্রপ খাইছে ভাই! পাইথন এরর: {str(e)[:120]}"

# --- Dashboard formatters ---
def create_progress_bar(percentage):
    filled = int(percentage // 10)
    return f"[{'█' * filled}{'░' * (10 - filled)}] {int(percentage)}%"

async def generate_premium_status():
    tot_lec = len(user_lectures)
    done_lec = sum(1 for v in user_lectures.values() if v == "Done")
    
    subs = {"P": {"tot_ch":0,"note":0,"practice":0,"exam":0,"tot_l":0,"done_l":0},
            "C": {"tot_ch":0,"note":0,"practice":0,"exam":0,"tot_l":0,"done_l":0},
            "M": {"tot_ch":0,"note":0,"practice":0,"exam":0,"tot_l":0,"done_l":0},
            "B": {"tot_ch":0,"note":0,"practice":0,"exam":0,"tot_l":0,"done_l":0}}
            
    for k, v in user_lectures.items():
        sk = k.split("_")[0][0]
        if sk in subs:
            subs[sk]["tot_l"] += 1
            if v == "Done": subs[sk]["done_l"] += 1
            
    for ck, info in user_chapters.items():
        sk = ck.split("_")[0][0]
        if sk in subs:
            subs[sk]["tot_ch"] += 1
            if info.get("note") == "Done": subs[sk]["note"] += 1
            if info.get("practice") == "Done": subs[sk]["practice"] += 1
            if info.get("exam") == "Done": subs[sk]["exam"] += 1
                    
    overall_prog = (done_lec / tot_lec * 100) if tot_lec > 0 else 0
    
    msg = "Status Dashboard\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"Overall Progress: {create_progress_bar(overall_prog)}\n"
    msg += f"Total Lectures: {tot_lec}  |  Completed: {done_lec}  |  Backlog: {tot_lec - done_lec}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for sk in ["P", "C", "M", "B"]:
        d = subs[sk]
        prog = (d["done_l"] / d["tot_l"] * 100) if d["tot_l"] > 0 else 0
        msg += f"{SUBJECT_ICONS[sk]} {SUBJECT_NAMES[sk]}: {create_progress_bar(prog)}\n"
        msg += f"            ├── Classes ── {d['done_l']}/{d['tot_l']}\n"
        msg += f"            ├── Note: {d['note']}/{d['tot_ch']}\n"
        msg += f"            ├── Practice: {d['practice']}/{d['tot_ch']}\n"
        msg += f"            └── Exam: {d['exam']}/{d['tot_ch']}\n\n"
        
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🎯 আজকের টার্গেটঃ {user_data['daily_target_raw']}\n\n"
    msg += f"🧠 কাইজেন গোলঃ {user_data['kaizen_goals']}\n"
    msg += "📊 লাস্ট ট্র্যাকিং লগঃ\n"
    
    if user_data["kaizen_logs"]:
        for log in user_data["kaizen_logs"][:4]:
            icon = "✅" if log.get("status") == "SUCCESS" else "❌"
            msg += f"  • {log.get('date')}: {log.get('goal')} -> {icon} ({log.get('text')})\n"
    else:
        msg += "  • এখনো কোনো লগ ডেটা জমা হয়নি।\n"
    msg += "  (জিতু ভাইয়া তোর প্যাটার্ন নজরে রাখছে!)\n"
    return msg

async def view_syllabus_tree(update: Update, context: ContextTypes.DEFAULT_TYPE, filter_arg=None):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    if not user_chapters and not user_lectures: return await update.message.reply_text("সিলেবাসে কোনো ডেটা নাই ভাই!")
    
    tree = {"P": {}, "C": {}, "M": {}, "B": {}}
    for ck, info in sorted(user_chapters.items()):
        sk = ck.split("_")[0][0]
        if filter_arg and filter_arg in ["P", "C", "M", "B"] and sk != filter_arg: continue
        if filter_arg and filter_arg in CHAPTER_NAMES and ck != filter_arg: continue
        if sk in tree: tree[sk][ck] = {"info": info, "lecs": []}
        
    for lk, stat in sorted(user_lectures.items()):
        parts = lk.split("_")
        ck = parts[0] + "_" + parts[1]
        sk = parts[0][0]
        if sk in tree and ck in tree[sk]:
            tree[sk][ck]["lecs"].append((parts[2], stat))
            
    msg = "Detailed Syllabus Report\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    has_data = False
    
    for sk in ["P", "C", "M", "B"]:
        if tree[sk]:
            has_data = True
            msg += f"{SUBJECT_ICONS[sk]} {SUBJECT_NAMES[sk]}\n\n"
            for ck, obj in tree[sk].items():
                ch_name = CHAPTER_NAMES.get(ck, ck)
                info = obj["info"]
                msg += f"📁 {ch_name} ({ck.split('_')[1]}) -> [Progress: {info.get('progress','0/0')}]\n"
                msg += f"  ├── Note: {info.get('note','Pending')} | Practice: {info.get('practice','Pending')} | Exam: {info.get('exam','Pending')}\n"
                msg += "  └── Lectures:\n"
                for idx, (l_num, stat) in enumerate(obj["lecs"]):
                    connector = "└──" if idx == len(obj["lecs"]) - 1 else "├──"
                    msg += f"      {connector} {l_num} ── {'Class Done' if stat=='Done' else 'Pending'}\n"
                msg += "\n"
                
    if not has_data: return await update.message.reply_text("কোনো সিলেবাস ডেটা খুঁজে পাওয়া যায়নি।")
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    await update.message.reply_text(msg)

# --- Keyboard Menus ---
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        ['Check Status', 'Set Target', 'Update Target'],
        ['Manage Kaizen', 'Update Kaizen', 'Syllabus Report'],
        ['Manage Syllabus']
    ], resize_keyboard=True)

def get_syllabus_keyboard():
    return ReplyKeyboardMarkup([
        ['Add New Lecture', 'Mark Class Done'],
        ['Mark Note Done', 'Mark Practice Done', 'Mark Exam Done'],
        ['Back to Main Menu']
    ], resize_keyboard=True)

# --- Handler Functions ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_data["current_state"] = "NORMAL"
    msg = "কিরে ভাই, আমি তোর মেন্টর জিতু ভাইয়া। V8 প্রফেশনাল মাস্টার এডিশন সাকসেসফুলি রানিং! কাজ শুরু কর।"
    await update.message.reply_text(msg, reply_markup=get_main_keyboard())

async def chapters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    msg = "📖 সিলেবাস কোড ডিকশনারী ম্যাপ\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    current_sub = ""
    for k, v in sorted(CHAPTER_NAMES.items()):
        sub_prefix = k.split("_")[0]
        if sub_prefix != current_sub:
            current_sub = sub_prefix
            msg += f"\n{SUBJECT_ICONS.get(current_sub[0], '📚')} {SUBJECT_NAMES.get(current_sub[0], current_sub)} ({current_sub})\n"
        msg += f"  • {k} -> {v}\n"
    await update.message.reply_text(msg)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    arg = context.args[0].upper() if context.args else None
    await view_syllabus_tree(update, context, filter_arg=arg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    text = update.message.text.strip()
    state = user_data["current_state"]

    # --- ১. গ্লোবাল মেনু নেভিগেশন ---
    if text == 'Check Status': 
        return await update.message.reply_text(await generate_premium_status())
    elif text == 'Syllabus Report': 
        return await view_syllabus_tree(update, context)
    elif text == 'Manage Syllabus': 
        user_data["current_state"] = "STATE_SYLLABUS_MENU"
        return await update.message.reply_text("সিলেবাস সিস্টেম কনফিগার কর:", reply_markup=get_syllabus_keyboard())
    elif text == 'Back to Main Menu': 
        user_data["current_state"] = "NORMAL"
        return await update.message.reply_text("🔙 মূল মেনু", reply_markup=get_main_keyboard())
    
    elif text == 'Set Target': 
        user_data["current_state"] = "WAITING_FOR_TARGET"
        return await update.message.reply_text("আজকের মিশন বা টার্গেটটা লিখে দে শুনি?")
    elif text == 'Update Target': 
        user_data["current_state"] = "WAITING_FOR_TARGET_UPDATE"
        return await update.message.reply_text("তোর আজকের টার্গেট কি শেষ করেছিস নাকি আংশিক হয়েছে? ক্যাজুয়ালি বল।")
    elif text == 'Manage Kaizen': 
        user_data["current_state"] = "WAITING_FOR_KAIZEN"
        return await update.message.reply_text("তোর নতুন কাইজেন গোল লাইফস্টাইল অভ্যাসটা কী সেট করতে চাস বল?")
    elif text == 'Update Kaizen': 
        user_data["current_state"] = "WAITING_FOR_KAIZEN_UPDATE"
        return await update.message.reply_text("কালকের কাইজেন গোলের অবস্থা বল, সফল নাকি ব্যর্থ? কী হয়েছিল খুলে বল।")

    # --- ২. সাব-মেনু কমান্ডস ---
    elif text == 'Add New Lecture': 
        user_data["current_state"] = "WAITING_FOR_ADD"
        return await update.message.reply_text("কোন লেকচারটা অ্যাড করতে চাস বল? রেঞ্জও দিতে পারিস (যেমন: P1 C2 L1 বা P1 C2 L1-10)")
    elif text == 'Mark Class Done': 
        user_data["current_state"] = "WAITING_FOR_CLASS"
        return await update.message.reply_text("কোন লেকচারের ক্লাস শেষ করলি? কোড দে (যেমন: P1 C2 L1)")
    elif text == 'Mark Note Done': 
        user_data["current_state"] = "WAITING_FOR_NOTE"
        return await update.message.reply_text("কোন চ্যাপ্টারের নোট কমপ্লিট? কোড দে (যেমন: P1 C2)")
    elif text == 'Mark Practice Done': 
        user_data["current_state"] = "WAITING_FOR_PRACTICE"
        return await update.message.reply_text("কোন চ্যাপ্টারের প্র্যাকটিস ডান? কোড দে (যেমন: P1 C2)")
    elif text == 'Mark Exam Done': 
        user_data["current_state"] = "WAITING_FOR_EXAM"
        return await update.message.reply_text("কোন চ্যাপ্টারের এক্সাম ডান? কোড দে (যেমন: P1 C2)")

    # --- ৩. ইন-মেনু কিবোর্ড ট্র্যাপ এভয়েডেন্স ---
    if state == "STATE_SYLLABUS_MENU":
        return await update.message.reply_text("ভাই, সিলেবাস কিবোর্ডের বাটনগুলো ব্যবহার কর অথবা 'Back to Main Menu' চেপে চলে যা।", reply_markup=get_syllabus_keyboard())

    # --- ৪. ওয়ান-টাইম লকিং সাব-স্টেট হ্যান্ডলার ---
    if state == "WAITING_FOR_TARGET":
        user_data["daily_target_raw"] = text
        user_data["current_state"] = "NORMAL"
        # V8: নতুন টার্গেট হিসেবে is_new=True পাঠানো হচ্ছে
        save_target_to_sheet("Pending", is_new=True)
        reply = generate_openrouter_chat(f"User set daily target: {text}", "User has set a daily target.")
        return await update.message.reply_text(reply, reply_markup=get_main_keyboard())

    elif state == "WAITING_FOR_TARGET_UPDATE":
        user_data["current_state"] = "NORMAL"
        reply = generate_openrouter_chat(text, "PARSING_TARGET_UPDATE")
        return await update.message.reply_text(reply, reply_markup=get_main_keyboard())

    elif state == "WAITING_FOR_KAIZEN":
        user_data["current_state"] = "NORMAL"
        reply = generate_openrouter_chat(f"New Lifestyle Habit: {text}", "PARSING_KAIZEN_SET")
        return await update.message.reply_text(reply, reply_markup=get_main_keyboard())

    elif state == "WAITING_FOR_KAIZEN_UPDATE":
        user_data["current_state"] = "NORMAL"
        reply = generate_openrouter_chat(text, "PARSING_KAIZEN_LOG")
        return await update.message.reply_text(reply, reply_markup=get_main_keyboard())

    # --- ৫. সিলেবাস সাব-মেনু ডাটা রাইটিং ---
    elif state == "WAITING_FOR_ADD":
        mode, ch_key, lec_info = parse_smart_shortcode(text)
        if not ch_key: 
            return await update.message.reply_text("কোড ঠিক নাই ভাই! উদাহরণ: P1 C2 L1 বা P1 C2 L1-10")
        
        if ch_key not in user_chapters: 
            user_chapters[ch_key] = {"progress": "0/0", "note": "Pending", "practice": "Pending", "exam": "Pending"}
        
        if mode == "RANGE":
            start_l, end_l = lec_info
            for i in range(start_l, end_l + 1):
                user_lectures[f"{ch_key}_L{i}"] = "Pending"
                post_lecture_to_sheet(ch_key, f"L{i}", "Pending")
            user_data["current_state"] = "STATE_SYLLABUS_MENU"
            return await update.message.reply_text(f"চ্যাপ্টারে L{start_l} থেকে L{end_l} বাল্ক লেকচার অ্যাড করা হয়েছে!", reply_markup=get_syllabus_keyboard())
        elif mode == "LECTURE":
            user_lectures[f"{ch_key}_{lec_info}"] = "Pending"
            post_lecture_to_sheet(ch_key, lec_info, "Pending")
            user_data["current_state"] = "STATE_SYLLABUS_MENU"
            return await update.message.reply_text(f"সিলেবাসে {ch_key} এর {lec_info} অ্যাড করা হয়েছে!", reply_markup=get_syllabus_keyboard())
        else: 
            return await update.message.reply_text("লেকচার নাম্বার বা রেঞ্জ উল্লেখ কর ভাই!")

    elif state == "WAITING_FOR_CLASS":
        mode, ch_key, lec_key = parse_smart_shortcode(text)
        if not ch_key or mode != "LECTURE": 
            return await update.message.reply_text("ভুল শর্টকোড! ট্রাই কর এভাবে: P1 C2 L1")
        full_lkey = f"{ch_key}_{lec_key}"
        user_lectures[full_lkey] = "Done"
        
        tot = sum(1 for k in user_lectures.keys() if k.startswith(ch_key+"_"))
        dn = sum(1 for k, v in user_lectures.items() if k.startswith(ch_key+"_") and v == "Done")
        if ch_key in user_chapters: user_chapters[ch_key]["progress"] = f"{dn}/{tot}"
        
        post_lecture_to_sheet(ch_key, lec_key, "Done")
        user_data["current_state"] = "STATE_SYLLABUS_MENU"
        return await update.message.reply_text("লেকচার ক্লাস কমপ্লিট মার্ক করা হয়েছে!", reply_markup=get_syllabus_keyboard())

    elif state in ["WAITING_FOR_NOTE", "WAITING_FOR_PRACTICE", "WAITING_FOR_EXAM"]:
        mode, ch_key, _ = parse_smart_shortcode(text)
        if not ch_key: 
            return await update.message.reply_text("ভুল চ্যাপ্টার শর্টকোড! ট্রাই কর এভাবে: P1 C2")
        task = state.split("_")[-1].lower()
        
        if ch_key not in user_chapters: 
            user_chapters[ch_key] = {"progress": "0/0", "note": "Pending", "practice": "Pending", "exam": "Pending"}
        user_chapters[ch_key][task] = "Done"
        
        post_chapter_task_to_sheet(ch_key, task, "Done")
        user_data["current_state"] = "STATE_SYLLABUS_MENU"
        return await update.message.reply_text(f"চ্যাপ্টারের {task.capitalize()} সফলভাবে ডান মার্ক করা হয়েছে!", reply_markup=get_syllabus_keyboard())

    # --- ৬. নরমাল কনভারসেশন চ্যাট ---
    reply = generate_openrouter_chat(text, "Respond organically as a mentor.")
    await update.message.reply_text(reply)

# --- Hourly Smart Reminder Engine ---
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    if user_data["daily_target_raw"] == "No target set yet." or "mission successful" in user_data["daily_target_raw"].lower(): 
        return
    current_hour = get_bd_time().hour
    if current_hour >= 0 and current_hour < 6: 
        return
    
    reply = generate_openrouter_chat("[SYSTEM: RUNNING HOURLY MONITOR CHECK]", "Hourly checking routine.")
    try: 
        await context.bot.send_message(chat_id=ALLOWED_CHAT_ID, text=reply)
    except Exception: pass

def run_dummy_server(): 
    HTTPServer(('', int(os.environ.get("PORT", 8080))), SimpleHTTPRequestHandler).serve_forever()

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    load_from_google_sheet()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", start))
    app.add_handler(CommandHandler("chapters", chapters_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    if app.job_queue: 
        app.job_queue.run_repeating(hourly_mentor_check, interval=3600, first=3600, name="hourly_tracker")
    
    print("✅ Jeetu Bhaiya AI V8 (Production Stable Edition) Running Successfully!")
    app.run_polling()

if __name__ == '__main__': 
    main()
