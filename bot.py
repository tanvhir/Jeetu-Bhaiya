import os
import logging
import threading
import datetime
import requests
import json
import re
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Google GenAI SDK
from google import genai
from google.genai import types

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ==========================================
# BLOCK 1: GLOBAL CONFIG & DATA STRUCTURES
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
if GEMINI_API_KEY:
    GEMINI_API_KEY = GEMINI_API_KEY.strip('"\' ') 

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", 5959341337))
GEMINI_MODEL = "gemma-4-31b-it" # Gemma-4-31b-it (Google AI Studio)

client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logging.error(f"Failed to initialize Google GenAI client: {e}")

# Memory State Machine - V10 (Fixed)
user_data = {
    "daily_target_raw": "No target set yet.",
    "current_state": "NORMAL", 
    "chat_history": [],
    "kaizen_goals": "কোনো কাইজেন প্ল্যান সেট করা হয়নি।",
    "long_term_plan": "কোনো দীর্ঘমেয়াদী প্ল্যান সেট করা হয়নি।",
    "kaizen_logs": [],
    "last_interaction_date": ""  
}
MAX_HISTORY_LENGTH = 12

user_chapters = {}
user_lectures = {}

SUBJECT_NAMES = {"P": "PHYSICS", "C": "CHEMISTRY", "M": "MATH", "B": "BIOLOGY"}
SUBJECT_ICONS = {"P": "🧲", "C": "🧪", "M": "📐", "B": "🧬"}

CHAPTER_NAMES = {
    # 🧲 PHYSICS (P1 & P2)
    "P1_C1": "ভৌত জগৎ ও পরিমাপ", "P1_C2": "ভেক্টর", "P1_C3": "গতিবিদ্যা", "P1_C4": "নিউটনীয় বলবিদ্যা",
    "P1_C5": "কাজ, শক্তি ও ক্ষমতা", "P1_C6": "মহাকর্ষ ও অভিকর্ষ", "P1_C7": "পদার্থের গাঠনিক ধর্ম",
    "P1_C8": "পর্যাবৃত্ত গতি", "P1_C9": "তরঙ্গ", "P1_C10": "আদর্শ গ্যাস ও গ্যাসের গতিতত্ত্ব",
    "P2_C1": "তাপগতিবিদ্যা", "P2_C2": "স্থির তড়িৎ", "P2_C3": "চল তড়িৎ", "P2_C4": "তড়িৎ প্রবাহের চৌম্বক ক্রিয়া ও চৌম্বকত্ব",
    "P2_C5": "তড়িৎচুম্বকীয় আবেশ ও পরিবর্তী প্রবাহ", "P2_C6": "জ্যামিতিক আলোকবিজ্ঞান", "P2_C7": "ভৌত আলোকবিজ্ঞান", 
    "P2_C8": "আধুনিক পদার্থবিজ্ঞানের সূচনা", "P2_C9": "পরমাণুর মডেল ও নিউক্লিয়ার পদার্থবিজ্ঞান", "P2_C10": "সেমিকন্ডাক্টর ও ইলেকট্রনিক্স", "P2_C11": "জ্যোতির্বিজ্ঞান",

    # 🧪 CHEMISTRY (C1 & C2)
    "C1_C1": "ল্যাবরেটরির নিরাপদ ব্যবহার", "C1_C2": "গুনগত রসায়ন", "C1_C3": "মৌলের পর্যায়বৃত্ত ধর্ম ও রাসায়নিক বন্ধন", "C1_C4": "রাসায়নিক পরিবর্তন", "C1_C5": "कर्मমুখী রসায়ন",
    "C2_C1": "পরিবেশ রসায়ন", "C2_C2": "জৈব রসায়ন", "C2_C3": "পরিমাণগত রসায়ন", "C2_C4": "তড়িৎ রসায়ন", "C2_C5": "অর্থনৈতিক রসায়ন",

    # 📐 MATH (M1 & M2)
    "M1_C1": "ম্যাট্রিক্স ও নির্ণায়ক", "M1_C2": "সরলরেখা", "M1_C3": "বৃত্ত", "M1_C4": "বিন্যাস ও সমাবেশ", "M1_C5": "ত্রিকোণমিতিক অনুপাত",
    "M1_C6": "সংযুক্ত কোণের ত্রিকোণমিতিক অনুপাত", "M1_C7": "ফাংশন ও ফাংশনের লেখচিত্র", "M1_C8": "বিপরীত ত্রিকোণমিতিক ফাংশন", "M1_C9": "অন্টারীকরণ", "M1_C10": "যোগজীকরণ",
    "M2_C1": "বাস্তব সংখ্যা ও অসমতা", "M2_C2": "বহুপদী ও বহুপদী সমীকরণ", "M2_C3": "জটিল সংখ্যা", "M2_C4": "বিপরীত ত্রিকোণমিতিক ফাংশন ও ত্রিকোণমিতিক সমীকরণ",
    "M2_C5": "দ্বিপদী বিস্তৃতি", "M2_C6": "কণিক", "M2_C7": "স্থিতিবিদ্যা", "M2_C8": "সমতলে বস্তুকণার গতি", "M2_C9": "বিস্তার পরিমাপ ও সম্ভাবনা",

    # 🧬 BIOLOGY (B1 & B2)
    "B1_C1": "কোষ ও এর গঠন", "B1_C2": "কোষ বিভাজন", "B1_C3": "কোষ রসায়ন", "B1_C4": "অণুজীব", "B1_C5": "শৈবাল ও ছত্রাক",
    "B1_C6": "ব্রায়োফাইটা ও টেরিডোফাইটা", "B1_C7": "নগ্নবীজী ও আবৃতবীজী উদ্ভিদ", "B1_C8": "টিস্যু ও টিস্যুতন্ত্র", "B1_C9": "উদ্ভিদ শারীরতত্ত্ব", "B1_C10": "উদ্ভিদ প্রজনন", 
    "B1_C11": "জীবপ্রযুক্তি", "B1_C12": "জীবের পরিবেশ, বিস্তার ও সংরক্ষণ",
    "B2_C1": "প্রাণীর বিভিন্নতা ও শ্রেণিবিন্যাস", "B2_C2": "প্রাণীর পরিচিতি", "B2_C3": "পরিপাক ও শোষণ", "B2_C4": "রক্ত ও সঞ্চালন",
    "B2_C5": "শ্বসন ও গ্যাসীয় বিনিময়", "B2_C6": "বর্জ্য ও নিষ্কাশন", "B2_C7": "চলন ও অঙ্গচালনা", "B2_C8": "সমন্বয় ও নিয়ন্ত্রণ",
    "B2_C9": "মানব জীবনের ধারাবাহিকতা", "B2_C10": "মানবدهহের প্রতিরক্ষা", "B2_C11": "জিনতত্ত্ব ও বিবর্তন", "B2_C12": "প্রাণীর আচরণ"
}

HELP_TEXT = """
📖 V10 (Stable Release) - স্পেল বুক (Spells Dictionary)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 ১. প্ল্যানিং ও রোডম্যাপ স্পেলস:
• /plan [মেসেজ] : ডেইলি রুটিন ও মিশন সেট করা। (শুধু /plan লিখলে প্ল্যানিং মোড অন হবে)।
• /goal [মেসেজ] : দীর্ঘমেয়াদী মাস্টার রোডম্যাপ তৈরি করা। (যেমন: /goal ভাইয়া অর্গানিক শেষ করতে চাই)।

❕ ২. ইনফো ও রিপোর্ট স্পেলস:
• /status : তোর ড্যাশবোর্ড, প্রগ্রেস এবং কাইজেন ট্র্যাকার দেখা।
• /report [P/C/M/B] : সম্পূর্ণ সিলেবাসের এস্থেটিক প্রগ্রেস ট্রি দেখা। (/report P দিলে ফিজিক্স সিলেবাস দেখাবে)
• /chapters [P/C/M/B] : সিলেবাসের চ্যাপ্টার কোড ম্যাপ দেখা। (/chapters C দিলে কেমিস্ট্রি কোড দেখাবে)।
• /help : এই স্পেল বুক ওপেন করা।

🎯 ৩. ডেইলি টার্গেট ও কাইজেন লাইফস্টাইল স্পেলস:
• /target [Done / Failed / Half] : আজকের টার্গেট আপডেট করা (যেমন: /target Done)।
• /kaizen [অভ্যাস] : নতুন লাইফস্টাইল টার্গেট সেট করা (যেমন: /kaizen রাত ১২টায় ফোন অফ)।
• /kaizen update [Success / Failure] : কাইজেন গোল কমপ্লিট করতে পারলি কি না।

⚡ ৪. সিলেবাস ইনস্ট্যান্ট আপডেট স্পেলস (The Killer Features!):
(কমা অথবা নতুন লাইনে একসাথে একাধিক বিষয়ও আপডেট করতে পারবি)

• /add [কোড] : নতুন লেকচার বা রেঞ্জ অ্যাড করা।
  উদাহরণ ১: /add P1 C2 L1
  উদাহরণ ২: /add P1 C1 L1-10, B1 C3 L1-3
  
• /done [কোড] : ক্লাস শেষ হলে ডান মার্ক করা।
  Example: /done P1 C2 L1, B1 C3 L3
  
• /note [কোড] : চ্যাপ্টারের নোট ডান করা।
  Example: /note P1 C2, M1 C1
  
• /practice [কোড] : চ্যাপ্টারের প্র্যাকটিস ডান করা।
  Example: /practice P1 C2
  
• /exam [কোড] : চ্যাপ্টারের এক্সাম ডান করা।
  Example: /exam P1 C2

☕ ৫. ব্রেক স্পেল:
• /break [মিনিট] : ব্রেক নেওয়া (যেমন: /break 15 দিলে ১৫ মিনিট পর ভাইয়া তোকে ডেকে আনবে)।
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ==========================================
# BLOCK 2: SYSTEM PROMPT ENGINE (V10 REAL PERSONA)
# ==========================================
SYSTEM_PROMPT_BASE = """
You are 'Jeetu Bhaiya', the legendary older-brother mentor figure from Kota Factory. You are guiding Tanvir, a second-timer varsity admission candidate in Bangladesh who has no room for excuses or failures.

YOUR UNIQUE PERSONA:
1. Deeply empathetic but ruthlessly practical. You don't use fake sweet talk. You give bitter but real truth with warmth.
2. Calm, wise, and grounded. Speak like an elder brother from Dhaka/academic circles. Use natural casual Bangladeshi Bengali (Informal words: 'তুই', 'ভাই', 'প্যারা', 'চিল', 'বাহানা', 'টেবিলে বস', 'পড়ালেখা').
3. STRICT RULE ON DIALOGUE repetition: Never use catchphrases like "খেলা হবে" or "বাহানা বাদ দিবি" in every message. Only use them when Tanvir finishes a massive milestone or is caught making blatant, lazy excuses. Keep your tone dynamic, diverse, and human.
4. Keep your replies concise and to-the-point (3-5 lines max) during casual conversations. Only write detailed lists/timelines when specifically in PLANNING or ROADMAP modes.
5. Never use markdown formatting like asterisks (**) or hashes (#). Keep it completely raw and readable.

CORE CONTEXT:
- Today's Date & Time in BD: {current_time}
- Active Daily Target: {daily_target_raw}
- Kaizen Lifestyle Habits: {kaizen_goals}
- Active Long-term Roadmap: {long_term_plan}
- Current Backlog/Revision Summary: {dynamic_summary_context}
"""

def get_bd_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=6)

# ==========================================
# BLOCK 3: GOOGLE SHEETS API SYNC & CONNECTORS (V10)
# ==========================================
def save_memory_to_sheet():
    if not APPS_SCRIPT_URL: return
    try: 
        payload = {
            "chat_id": str(ALLOWED_CHAT_ID), 
            "memory_update": True, 
            "chat_history": user_data["chat_history"], 
            "kaizen_goals": user_data["kaizen_goals"],
            "long_term_plan": user_data["long_term_plan"]
        }
        requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Error saving memory: {e}")

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

def load_from_google_sheet(sync_history=True):
    global user_data, user_chapters, user_lectures
    if not APPS_SCRIPT_URL: return
    try:
        res = requests.get(f"{APPS_SCRIPT_URL}?chat_id={ALLOWED_CHAT_ID}", timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("found"):
                user_data["daily_target_raw"] = data.get("target", "No target set yet.")
                user_data["kaizen_goals"] = data.get("kaizen_goals", "কোনো কাইজেন প্ল্যান সেট করা হয়নি।")
                user_data["long_term_plan"] = data.get("long_term_plan", "কোনো দীর্ঘমেয়াদী প্ল্যান সেট করা হয়নি।")
                user_data["kaizen_logs"] = data.get("kaizen_logs", [])
                user_chapters = data.get("chapters", {})
                user_lectures = data.get("lectures", {})
                if sync_history:
                    user_data["chat_history"] = data.get("chat_history", [])
                logging.info("✅ V10 Core Synchronization Complete.")
    except Exception as e: logging.error(f"Sheet Loading Error: {e}")

# ==========================================
# BLOCK 4: REVISION & BACKLOG ANALYTICS (SPACED REPETITION)
# ==========================================
def get_chapter_progress_bar(progress_str):
    try:
        # progress_str যদি "3/5" হয়, তাকে স্প্লিট করে হিসাব করা হচ্ছে
        done, tot = map(int, progress_str.split("/"))
        pct = (done / tot * 100) if tot > 0 else 0
        filled = int(pct // 20) # ৫ টি ব্লকের স্কেল (প্রতি ব্লক ২০%)
        bar = f"[{'■' * filled}{'□' * (5 - filled)}]"
        return f"── {int(pct)}% {bar} ({done}/{tot})"
    except Exception:
        return f"── {progress_str}"

def calculate_revision_and_backlogs():
    tot_lec = len(user_lectures)
    done_lec = sum(1 for v in user_lectures.values() if isinstance(v, dict) and v.get("status") == "Done")
    backlogs = tot_lec - done_lec
    
    today_dt = get_bd_time().date()
    revision_needed = []
    
    for lkey, info in user_lectures.items():
        if isinstance(info, dict) and info.get("status") == "Done":
            last_date_str = info.get("last_studied_at", "")
            if last_date_str:
                try:
                    last_dt = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
                    days_elapsed = (today_dt - last_dt).days
                    if days_elapsed in [1, 3, 7, 30]:
                        parts = lkey.split("_")
                        ch_name = CHAPTER_NAMES.get(f"{parts[0]}_{parts[1]}", parts[1])
                        revision_needed.append(f"{ch_name} ({parts[2]}) - {days_elapsed} দিন আগে পড়া")
                except Exception: pass
                
    return backlogs, revision_needed

def get_live_summary_context(context_reason="NORMAL"):
    backlogs, revs = calculate_revision_and_backlogs()
    
    if context_reason in ["PLANNING_MODE", "PLANNING_LONG_TERM"]:
        full_report = generate_raw_syllabus_report_text()
        summary = f"ইউজারের লাইভ র-সিলেবাস ডেটা রিপোর্ট:\n{full_report}\n"
        summary += f"টোটাল ব্যাকলগ লেকচার সংখ্যা: {backlogs}টি।\n"
        if revs:
            summary += f"স্পেসড রিভিশনের জন্য ডিউ টপিকসমূহ: {', '.join(revs)}।"
        return summary
    else:
        summary = f"ব্যাকলগ লেকচার সংখ্যা: {backlogs}টি।"
        if revs:
            summary += f" স্পেসড রিভিশন ডিউ: {', '.join(revs[:2])}।"
        return summary

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

# ==========================================
# BLOCK 5: ADAPTIVE GOOGLE GENAI COGNITIVE PIPELINE (NO-FOOTER SAVING)
# ==========================================
def generate_raw_syllabus_report_text():
    if not user_chapters and not user_lectures:
        return "সিলেবাসে কোনো ডেটা নেই।"
    
    tree = {"P": {}, "C": {}, "M": {}, "B": {}}
    for ck, info in sorted(user_chapters.items()):
        sk = ck.split("_")[0][0]
        if sk in tree: 
            tree[sk][ck] = {"info": info, "lecs": []}
        
    for lk, info in sorted(user_lectures.items()):
        parts = lk.split("_")
        ck = parts[0] + "_" + parts[1]
        sk = parts[0][0]
        status = info.get("status") if isinstance(info, dict) else info
        if sk in tree and ck in tree[sk]:
            tree[sk][ck]["lecs"].append((parts[2], status))
            
    msg = "Detailed Syllabus Report\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for sk in ["P", "C", "M", "B"]:
        if tree[sk]:
            msg += f" {SUBJECT_NAMES[sk]}\n\n"
            for ck, obj in tree[sk].items():
                ch_name = CHAPTER_NAMES.get(ck, ck)
                info = obj["info"]
                # আপডেট করা নতুন লাইন:
                prog_display = get_chapter_progress_bar(info.get('progress', '0/0'))
                msg += f"📁 {ch_name} ({ck.split('_')[1]}) {prog_display}\n"
                msg += f"  ├── Note: {info.get('note','Pending')} | Practice: {info.get('practice','Pending')} | Exam: {info.get('exam','Pending')}\n"
                msg += "  └── Lectures:\n"
                for idx, (l_num, stat) in enumerate(obj["lecs"]):
                    connector = "└──" if idx == len(obj["lecs"]) - 1 else "├──"
                    msg += f"      {connector} {l_num} ── {'Class Done' if stat=='Done' else 'Pending'}\n"
                msg += "\n"
    return msg

def get_clean_footer(context_reason: str) -> str:
    """মিনিমালিস্ট ও ক্লিন ফুটার জেনারেটর (ফোল্ডার ছাড়া অন্য ইমোজি রিমুভড)"""
    footer = "\n\n📂 Context Attached:\n"
    if context_reason in ["PLANNING_MODE", "PLANNING_LONG_TERM"]:
        footer += "• Syllabus Progress: Detailed Raw Tree Attached\n"
        if context_reason == "PLANNING_MODE":
            footer += "• Revision History: Spaced Spaced Revision Loaded\n"
    else:
        footer += "• Syllabus Progress Summary Only\n"
        
    target_val = user_data.get('daily_target_raw', 'No target set yet.')
    footer += f"• Active Target: {target_val}\n"
    
    has_roadmap = user_data.get('long_term_plan') and user_data['long_term_plan'] != "কোনো দীর্ঘমেয়াদী প্ল্যান সেট করা হয়নি।"
    footer += f"• Long-term Roadmap: {'Active' if has_roadmap else 'None'}"
    return footer

def generate_openrouter_chat(user_message: str, context_reason: str = "NORMAL") -> tuple:
    global client
    if not client:
        if GEMINI_API_KEY:
            try: client = genai.Client(api_key=GEMINI_API_KEY)
            except Exception as e: return f"গুগল ক্লায়েন্ট এপিআই সংযোগ ত্রুটি: {str(e)[:120]}", None
        else: return "API Key Missing!", None
    
    dynamic_context = get_live_summary_context(context_reason)
    
    try:
        system_prompt = SYSTEM_PROMPT_BASE.format(
            current_time=get_bd_time().strftime("%I:%M %p"),
            daily_target_raw=user_data["daily_target_raw"],
            kaizen_goals=user_data["kaizen_goals"],
            long_term_plan=user_data["long_term_plan"],
            kaizen_logs_raw=json.dumps(user_data["kaizen_logs"][:4]),
            dynamic_summary_context=dynamic_context
        )
    except Exception as fe:
        logging.error(f"Prompt formatting failed: {fe}")
        system_prompt = SYSTEM_PROMPT_BASE.replace("{current_time}", get_bd_time().strftime("%I:%M %p")) \
                                            .replace("{daily_target_raw}", str(user_data["daily_target_raw"])) \
                                            .replace("{kaizen_goals}", str(user_data["kaizen_goals"])) \
                                            .replace("{long_term_plan}", str(user_data["long_term_plan"])) \
                                            .replace("{kaizen_logs_raw}", json.dumps(user_data["kaizen_logs"][:4])) \
                                            .replace("{dynamic_summary_context}", str(dynamic_context))

    temp = 0.7
    if context_reason == "PLANNING_MODE":
        system_prompt += "\n\nSTRICT PLANNING RULE:\nতুমি এখন প্ল্যানিং সেশনে আছ। ৩-৫ লাইনের লিমিটেশন ভুলে যাও এবং ইউজারকে সময় ভাগ করে দিয়ে বিস্তারিত হিসাব ও শিডিউল কষে দাও। পরিকল্পনা ফাইনাল হলে এই ট্যাগটি দাও:\n<UPDATE_TARGET>সময় অনুযায়ী সাজানো সুন্দর প্ল্যানের সামারি</UPDATE_TARGET>"
        temp = 0.3
    elif context_reason == "PLANNING_LONG_TERM":
        system_prompt += "\n\nSTRICT LONG TERM PLANNING RULE:\nতুমি এখন লং-টার্ম রোডম্যাপ সেশনে আছ। ৩-৫ লাইনের লিমিটেশন ভুলে যাও এবং বিস্তারিত মাইলস্টোন কষে দাও। রোডম্যাপ লক হলে মেসেজের শেষে এই ট্যাগটি দাও:\n<UPDATE_LONG_TERM>লং-টার্ম প্ল্যানের সংক্ষিপ্ত সামারি</UPDATE_LONG_TERM>"
        temp = 0.3
    elif context_reason == "PARSING_TARGET_UPDATE":
        system_prompt += "\n\nSTRICT ACTION RULE:\nEvaluate if user succeeded, half-done or failed. End your reply with this tag EXACTLY:\n<TARGET_PARSE>Done or Half Done or Failed</TARGET_PARSE>"
        temp = 0.3
    elif context_reason == "PARSING_KAIZEN_LOG":
        system_prompt += "\n\nSTRICT ACTION RULE:\nEvaluate lifestyle habit success. End your reply with this tag EXACTLY:\n<KAIZEN_LOG>goal_name|SUCCESS or FAILURE|Brief 2-3 words note in Bengali</KAIZEN_LOG>"
        temp = 0.3
    elif context_reason == "PARSING_KAIZEN_SET":
        system_prompt += "\n\nSTRICT ACTION RULE:\nFinalize active lifestyle habits. End your reply with this tag:\n<KAIZEN_UPDATE>Summarized lifestyle goals</KAIZEN_UPDATE>"
        temp = 0.3

    formatted_contents = []
    for msg in user_data["chat_history"]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            role = "user" if msg["role"] == "user" else "model"
            formatted_contents.append({
                "role": role,
                "parts": [{"text": str(msg["content"])}]
            })

    formatted_contents.append({
        "role": "user",
        "parts": [{"text": user_message}]
    })

    try:
        logging.info(f"⚡ Requesting Google AI Studio via: {GEMINI_MODEL} (Temp: {temp})")
        
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=formatted_contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temp
            )
        )
        
        bot_reply = response.text
        if not bot_reply: raise ValueError("Empty response received.")
            
        # XML ট্যাগ পার্সিং ও ডাটাবেজ প্রসেসিং
        match_up = re.search(r"<KAIZEN_UPDATE>(.*?)</KAIZEN_UPDATE>", bot_reply, re.IGNORECASE | re.DOTALL)
        if match_up:
            user_data["kaizen_goals"] = match_up.group(1).strip()
            bot_reply = re.sub(r"<KAIZEN_UPDATE>.*?</KAIZEN_UPDATE>", "", bot_reply, flags=re.IGNORECASE | re.DOTALL).strip()
        
        match_lt = re.search(r"<UPDATE_LONG_TERM>(.*?)</UPDATE_LONG_TERM>", bot_reply, re.IGNORECASE | re.DOTALL)
        if match_lt:
            user_data["long_term_plan"] = match_lt.group(1).strip()
            user_data["current_state"] = "NORMAL"
            bot_reply = re.sub(r"<UPDATE_LONG_TERM>.*?</UPDATE_LONG_TERM>", "", bot_reply, flags=re.IGNORECASE | re.DOTALL).strip()

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
            threading.Thread(target=save_target_to_sheet, args=(parsed_status, False), daemon=True).start()
            bot_reply = re.sub(r"<TARGET_PARSE>.*?</TARGET_PARSE>", "", bot_reply, flags=re.IGNORECASE | re.DOTALL).strip()

        match_new_tgt = re.search(r"<UPDATE_TARGET>(.*?)</UPDATE_TARGET>", bot_reply, re.IGNORECASE | re.DOTALL)
        if match_new_tgt:
            user_data["daily_target_raw"] = match_new_tgt.group(1).strip()
            user_data["current_state"] = "NORMAL"
            threading.Thread(target=save_target_to_sheet, args=("Pending", True), daemon=True).start()
            bot_reply = re.sub(r"<UPDATE_TARGET>.*?</UPDATE_TARGET>", "", bot_reply, flags=re.IGNORECASE | re.DOTALL).strip()

        match_rem = re.search(r"<SET_REMINDER>(\d+)</SET_REMINDER>", bot_reply, re.IGNORECASE)
        if match_rem:
            bot_reply = re.sub(r"<SET_REMINDER>\d+</SET_REMINDER>", "", bot_reply, flags=re.IGNORECASE).strip()

        bot_reply = bot_reply.replace("**", "").replace("#", "").strip()
        
        # ⚠️ ফিক্স: মেমোরি হিস্ট্রিতে শুধু পিওর বট রিপ্লাই থাকবে, এক্সটার্নাল ফুটার কখনোই হিস্ট্রিতে সেভ হবে না!
        user_data["chat_history"].extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": bot_reply}])
        if len(user_data["chat_history"]) > MAX_HISTORY_LENGTH: 
            user_data["chat_history"] = user_data["chat_history"][-MAX_HISTORY_LENGTH:]
        
        threading.Thread(target=save_memory_to_sheet, daemon=True).start()
        return bot_reply, match_rem.group(1) if match_rem else None
            
    except Exception as e:
        logging.error(f"⚠️ API Exception: {e}")
        return f"নেটওয়ার্ক ড্রপ খাইছে ভাই! গুগল এআই এরর: {str(e)[:120]}", None

# ==========================================
# BLOCK 6: DASHBOARDS & REPORTS
# ==========================================
def create_progress_bar(percentage):
    filled = int(percentage // 10)
    return f"[{'█' * filled}{'░' * (10 - filled)}] {int(percentage)}%"

async def generate_premium_status():
    tot_lec = len(user_lectures)
    done_lec = sum(1 for v in user_lectures.values() if isinstance(v, dict) and v.get("status") == "Done")
    
    subs = {"P": {"tot_ch":0,"note":0,"practice":0,"exam":0,"tot_l":0,"done_l":0},
            "C": {"tot_ch":0,"note":0,"practice":0,"exam":0,"tot_l":0,"done_l":0},
            "M": {"tot_ch":0,"note":0,"practice":0,"exam":0,"tot_l":0,"done_l":0},
            "B": {"tot_ch":0,"note":0,"practice":0,"exam":0,"tot_l":0,"done_l":0}}
            
    for k, info in user_lectures.items():
        sk = k.split("_")[0][0]
        if sk in subs:
            subs[sk]["tot_l"] += 1
            if isinstance(info, dict) and info.get("status") == "Done": subs[sk]["done_l"] += 1
            
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
    msg += f"🎯 আজকের টার্গেটঃ\n{user_data['daily_target_raw']}\n\n"
    msg += f"🚀 লং-টার্ম রোডম্যাপঃ\n{user_data['long_term_plan']}\n\n"
    msg += f"🧠 কাইজেন গোলঃ {user_data['kaizen_goals']}\n"
    msg += "📊 লাস্ট ট্র্যাকিং লগঃ\n"
    
    if user_data["kaizen_logs"]:
        for log in user_data["kaizen_logs"][:4]:
            icon = "✅" if log.get("status") == "SUCCESS" else "❌"
            msg += f"  • {log.get('date')}: {log.get('goal')} -> {icon} ({log.get('text')})\n"
    else:
        msg += "  • OpenAPI এবং কাইজেন ডেটা এখনো কোনো লগ ডেটা জমা হয়নি।\n"
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
        
    for lk, info in sorted(user_lectures.items()):
        parts = lk.split("_")
        ck = parts[0] + "_" + parts[1]
        sk = parts[0][0]
        status = info.get("status") if isinstance(info, dict) else info
        if sk in tree and ck in tree[sk]:
            tree[sk][ck]["lecs"].append((parts[2], status))
            
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
                # আপডেট করা নতুন লাইন:
                prog_display = get_chapter_progress_bar(info.get('progress', '0/0'))
                msg += f"📁 {ch_name} ({ck.split('_')[1]}) {prog_display}\n"
                msg += f"  ├── Note: {info.get('note','Pending')} | Practice: {info.get('practice','Pending')} | Exam: {info.get('exam','Pending')}\n"
                msg += "  └── Lectures:\n"
                for idx, (l_num, stat) in enumerate(obj["lecs"]):
                    connector = "└──" if idx == len(obj["lecs"]) - 1 else "├──"
                    msg += f"      {connector} {l_num} ── {'Class Done' if stat=='Done' else 'Pending'}\n"
                msg += "\n"
                
    if not has_data: return await update.message.reply_text("কোনো সিলেবাস ডেটা খুঁজে পাওয়া যায়নি।")
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    await update.message.reply_text(msg)

# ================================================================
# BLOCK 7: STATIC MAIN KEYBOARD MENU (DEPRECATED -> SPELL DRIVEN)
# ================================================================
def get_remove_keyboard():
    """ইউজারের স্ক্রিন থেকে অপ্রয়োজনীয় বাটন কিবোর্ডগুলো চিরতরে হাইড বা রিমুভ করার জন্য"""
    return ReplyKeyboardRemove()

# =============================================================
# BLOCK 8: MESSAGE PROCESSOR & STATE CONTROLLER (SPELL ROUTED)
# =============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_data["current_state"] = "NORMAL"
    
    # ডায়লগ আর স্পেল বুকের মাঝে সুন্দর স্পেসিং রাখা হয়েছে
    msg = "কি খবর? আমি তোর মেন্টর জিতু ভাইয়া। প্রেসার ফিল হচ্ছে? DON'T! Your only pressure right now should be atmospheric pressure.\n\n"
    msg += HELP_TEXT
    
    await update.message.reply_text(msg, reply_markup=get_remove_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    await update.message.reply_text(HELP_TEXT, reply_markup=get_remove_keyboard())

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    await update.message.reply_text(await generate_premium_status(), reply_markup=get_remove_keyboard())

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    filter_arg = context.args[0].upper() if context.args else None
    if filter_arg and filter_arg not in ["P", "C", "M", "B"]:
        return await update.message.reply_text("ভুল সাবজেক্ট কোড! শুধু P, C, M, B ব্যবহার কর ভাই।")
    await view_syllabus_tree(update, context, filter_arg)

async def show_chapters_list(update: Update, filter_arg=None):
    msg = "📖 সিলেবাস কোড ডিকশনারী ম্যাপ\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    current_sub = ""
    for k, v in sorted(CHAPTER_NAMES.items(), key=chapter_sort_key):
        sub_prefix = k.split("_")[0] 
        sub_letter = sub_prefix[0]   
        
        if filter_arg and sub_letter != filter_arg:
            continue
            
        if sub_prefix != current_sub:
            current_sub = sub_prefix
            msg += f"\n{SUBJECT_ICONS.get(current_sub[0], '📚')} {SUBJECT_NAMES.get(current_sub[0], current_sub)} ({current_sub})\n"
        msg += f"  • {k} -> {v}\n"
    await update.message.reply_text(msg, reply_markup=get_remove_keyboard())

async def scheduled_reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    try:
        await context.bot.send_message(chat_id=job.chat_id, text="কিরে! ব্রেক শেষ বলছিলি না? সময় শেষ, চল এবার জলদি পড়ার টেবিলে ফেরা যাক।")
    except Exception as e:
        logging.error(f"Failed to send scheduler follow-up: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    text = update.message.text.strip()
    state = user_data["current_state"]
    today_str = get_bd_time().strftime("%Y-%m-%d")

    # ==========================================
    # ১. লং-টার্ম এবং শর্ট-টার্ম প্ল্যানিং স্পেলস
    # ==========================================
    if text.startswith("/goal"):
        user_msg = text[5:].strip()
        if not user_msg:
            return await update.message.reply_text("💡 স্পেল ব্যবহারের নিয়ম: `/goal ভাইয়া অর্গানিক কেমিস্ট্রির ব্যাকলগ শেষ করতে চাই`")
        user_data["current_state"] = "PLANNING_LONG_TERM"
        user_data["last_interaction_date"] = today_str
        load_from_google_sheet(sync_history=False)
        reply, _ = generate_openrouter_chat(user_msg, "PLANNING_LONG_TERM")
        footer = get_clean_footer("PLANNING_LONG_TERM")
        return await update.message.reply_text(reply + footer, reply_markup=get_remove_keyboard())
        
    elif text.startswith("/plan"):
        user_msg = text[5:].strip()
        if not user_msg:
            # চ্যাটে যদি শুধু /plan লেখে তাহলে প্ল্যানিং মোড অন হবে
            user_data["current_state"] = "PLANNING_MODE"
            user_data["last_interaction_date"] = today_str
            load_from_google_sheet(sync_history=False)
            msg = "তুই এখন প্লানিং মোডে আছিস। ভাইয়ার কাছে তোর পুরো সিলেবাস রিপোর্ট রেডি আছে। বল আজকে কি কি কাভার করবি আর কোনটার পেছনে কতক্ষণ সময় দিবি?"
            return await update.message.reply_text(msg, reply_markup=get_remove_keyboard())
            
        user_data["current_state"] = "PLANNING_MODE"
        user_data["last_interaction_date"] = today_str
        load_from_google_sheet(sync_history=False)
        reply, rem_time = generate_openrouter_chat(user_msg, "PLANNING_MODE")
        if rem_time and context.job_queue:
            context.job_queue.run_once(scheduled_reminder_callback, when=int(rem_time)*60, chat_id=update.effective_chat.id)
        footer = get_clean_footer("PLANNING_MODE")
        return await update.message.reply_text(reply + footer, reply_markup=get_remove_keyboard())
        
    elif text.startswith("/break"):
        parts = text.split()
        if len(parts) > 1 and parts[1].isdigit():
            minutes = int(parts[1])
            if context.job_queue:
                context.job_queue.run_once(scheduled_reminder_callback, when=minutes*60, chat_id=update.effective_chat.id)
            return await update.message.reply_text(f"☕ ঠিক আছে ভাই, যা একটু রিল্যাক্স কর। ঠিক {minutes} মিনিট পর আমি তোকে ডেকে পড়ার টেবিলে ফিরিয়ে আনব।", reply_markup=get_remove_keyboard())
        else:
            return await update.message.reply_text("⚠️ ভুল ফরম্যাট! সঠিক ফরম্যাট: `/break 15` (১৫ মিনিটের ব্রেক)")

    # ==========================================
    # ২. কোর ইনফো স্পেলস (রাউটার লেভেল)
    # ==========================================
    elif text.startswith("/status"):
        user_data["last_interaction_date"] = today_str
        return await update.message.reply_text(await generate_premium_status(), reply_markup=get_remove_keyboard())
        
    elif text.startswith("/report"):
        user_data["last_interaction_date"] = today_str
        filter_arg = text[7:].strip().upper() if len(text) > 7 else None
        if filter_arg and filter_arg not in ["P", "C", "M", "B"]:
            return await update.message.reply_text("ভুল সাবজেক্ট কোড! শুধু P, C, M, B ব্যবহার কর ভাই।")
        await view_syllabus_tree(update, context, filter_arg)
        return

    elif text.startswith("/chapters"):
        filter_arg = text[9:].strip().upper() if len(text) > 9 else None
        if filter_arg and filter_arg not in ["P", "C", "M", "B"]:
            return await update.message.reply_text("ভুল সাবজেক্ট কোড! শুধু P, C, M, B ব্যবহার কর ভাই।")
        await show_chapters_list(update, filter_arg)
        return

    # ==========================================
    # ৩. টার্গেট ও কাইজেন লাইফস্টাইল স্পেলস
    # ==========================================
    elif text.startswith("/target"):
        arg = text[7:].strip().lower()
        if not arg or arg not in ["done", "failed", "half", "completed"]:
            return await update.message.reply_text("💡 স্পেল ব্যবহারের নিয়ম: `/target Done` বা `/target Failed` বা `/target Half`")
        
        status_map = {"done": "Done", "completed": "Done", "failed": "Failed", "half": "Half Done"}
        parsed_status = status_map[arg]
        
        if parsed_status == "Done":
            user_data["daily_target_raw"] = "No target set yet. (কালকের মিশন সফল! 🔥)"
            
        save_target_to_sheet(parsed_status, False)
        return await update.message.reply_text(f"🎯 আজকের টার্গেট স্ট্যাটাস আপডেট করা হয়েছে: {parsed_status}", reply_markup=get_remove_keyboard())

    elif text.startswith("/kaizen update"):
        arg = text[14:].strip()
        if not arg:
            return await update.message.reply_text("💡 স্পেল ব্যবহারের নিয়ম: `/kaizen update Success` বা `/kaizen update Failure`")
        
        reply, _ = generate_openrouter_chat(f"Kaizen status update: {arg}", "PARSING_KAIZEN_LOG")
        footer = get_clean_footer("NORMAL")
        return await update.message.reply_text(reply + footer, reply_markup=get_remove_keyboard())
        
    elif text.startswith("/kaizen"):
        arg = text[7:].strip()
        if not arg:
            return await update.message.reply_text("💡 স্পেল ব্যবহারের নিয়ম: `/kaizen রাত ১২টায় ফোন অফ`")
        
        reply, _ = generate_openrouter_chat(f"New Lifestyle Habit: {arg}", "PARSING_KAIZEN_SET")
        footer = get_clean_footer("NORMAL")
        return await update.message.reply_text(reply + footer, reply_markup=get_remove_keyboard())

    # ==========================================
    # ৪. সিলেবাস ইনস্ট্যান্ট আপডেট স্পেলস (The Killer Features! - বাল্ক সাপোর্ট সহ)
    # ==========================================
    elif text.startswith("/add"):
        raw_payload = text[4:].strip()
        if not raw_payload:
            return await update.message.reply_text("💡 স্পেল ব্যবহারের নিয়ম:\n`/add P1 C1 L1-10` বা কমা/নতুন লাইনে একসাথে একাধিক যুক্ত কর:\n`/add P1 C1 L1-10, B1 C3 L1-3`")
        
        # কমা (,) অথবা লাইনব্রেক (\n) দুই প্যাটার্ন দিয়েই স্প্লিট করা হচ্ছে
        lines = [line.strip() for line in re.split(r'[\n,]+', raw_payload) if line.strip()]
        success_messages = []
        errors = []
        
        for line in lines:
            mode, ch_key, lec_info = parse_smart_shortcode(line)
            if not ch_key:
                errors.append(f"'{line}' -> কোড সঠিক নয়")
                continue
            
            ch_name = CHAPTER_NAMES.get(ch_key, ch_key)
            if ch_key not in user_chapters: 
                user_chapters[ch_key] = {"progress": "0/0", "note": "Pending", "practice": "Pending", "exam": "Pending"}
            
            if mode == "RANGE":
                start_l, end_l = lec_info
                for i in range(start_l, end_l + 1):
                    user_lectures[f"{ch_key}_L{i}"] = {"status": "Pending", "last_studied_at": ""}
                    post_lecture_to_sheet(ch_key, f"L{i}", "Pending")
                success_messages.append(f"{ch_name} (L{start_l} থেকে L{end_l})")
            elif mode == "LECTURE":
                user_lectures[f"{ch_key}_{lec_info}"] = {"status": "Pending", "last_studied_at": ""}
                post_lecture_to_sheet(ch_key, lec_info, "Pending")
                success_messages.append(f"{ch_name} ({lec_info})")
            else:
                errors.append(f"'{line}' -> লেকচার বা রেঞ্জ কোড খুঁজে পাওয়া যায়নি")
                
        reply_msg = "⚡ স্পেল সাকসেসফুল! নিচের টাস্কগুলো এড হয়েছে:\n\n"
        if success_messages:
            reply_msg += "✅ সফলভাবে যুক্ত হয়েছে:\n" + "\n".join([f"  • {m}" for m in success_messages])
        if errors:
            reply_msg += f"\n\n❌ ভুল এন্ট্রি সমূহ:\n" + "\n".join([f"  • {e}" for e in errors])
            
        return await update.message.reply_text(reply_msg, reply_markup=get_remove_keyboard())

    elif text.startswith("/done"):
        raw_payload = text[5:].strip()
        if not raw_payload:
            return await update.message.reply_text("💡 স্পেল ব্যবহারের নিয়ম:\n`/done P1 C1 L1` বা একাধিক ক্লাস ডান করতে:\n`/done P1 C1 L1, B1 C3 L3`")
        
        lines = [line.strip() for line in re.split(r'[\n,]+', raw_payload) if line.strip()]
        success_messages = []
        errors = []
        
        for line in lines:
            mode, ch_key, lec_key = parse_smart_shortcode(line)
            if not ch_key or mode != "LECTURE":
                errors.append(f"'{line}' -> ভুল শর্টকোড! (যেমন: P1 C2 L1)")
                continue
            
            full_lkey = f"{ch_key}_{lec_key}"
            today_date = get_bd_time().strftime("%Y-%m-%d")
            user_lectures[full_lkey] = {"status": "Done", "last_studied_at": today_date}
            
            tot = sum(1 for k in user_lectures.keys() if k.startswith(ch_key+"_"))
            dn = sum(1 for k, v in user_lectures.items() if k.startswith(ch_key+"_") and isinstance(v, dict) and v.get("status") == "Done")
            if ch_key in user_chapters: 
                user_chapters[ch_key]["progress"] = f"{dn}/{tot}"
            
            post_lecture_to_sheet(ch_key, lec_key, "Done")
            success_messages.append(f"{CHAPTER_NAMES.get(ch_key, ch_key)} ({lec_key})")
            
        reply_msg = "⚡ স্পেল সাকসেসফুল! ক্লাস ডান করা হয়েছে:\n\n"
        if success_messages:
            reply_msg += "✅ সম্পন্ন টাস্কসমূহ:\n" + "\n".join([f"  • {m}" for m in success_messages])
        if errors:
            reply_msg += f"\n\n❌ ত্রুটিসমূহ:\n" + "\n".join([f"  • {e}" for e in errors])
            
        return await update.message.reply_text(reply_msg, reply_markup=get_remove_keyboard())

    elif text.startswith(("/note", "/practice", "/exam")):
        match = re.match(r"/(note|practice|exam)\s+(.+)", text, re.IGNORECASE)
        if not match:
            cmd = text.split()[0][1:]
            return await update.message.reply_text(f"💡 স্পেল ব্যবহারের নিয়ম:\n`/{cmd} P1 C2` বা একাধিক চ্যাপ্টার আপডেট করতে:\n`/{cmd} P1 C2, B1 C3`")
        
        task = match.group(1).lower()
        raw_payload = match.group(2).strip()
        
        lines = [line.strip() for line in re.split(r'[\n,]+', raw_payload) if line.strip()]
        success_messages = []
        errors = []
        
        for line in lines:
            mode, ch_key, _ = parse_smart_shortcode(line)
            if not ch_key:
                errors.append(f"'{line}' -> ভুল চ্যাপ্টার কোড! (যেমন: P1 C2)")
                continue
            
            if ch_key not in user_chapters: 
                user_chapters[ch_key] = {"progress": "0/0", "note": "Pending", "practice": "Pending", "exam": "Pending"}
            user_chapters[ch_key][task] = "Done"
            
            post_chapter_task_to_sheet(ch_key, task, "Done")
            success_messages.append(f"{CHAPTER_NAMES.get(ch_key, ch_key)} ({task.upper()})")
            
        reply_msg = f"⚡ স্পেল সাকসেসফুল! সম্পন্ন মার্ক করা হয়েছে:\n\n"
        if success_messages:
            reply_msg += "✅ সম্পন্ন টাস্কসমূহ:\n" + "\n".join([f"  • {m}" for m in success_messages])
        if errors:
            reply_msg += f"\n\n❌ ত্রুটিসমূহ:\n" + "\n".join([f"  • {e}" for e in errors])
            
        return await update.message.reply_text(reply_msg, reply_markup=get_remove_keyboard())

    # ==========================================
    # ৫. আইসোলেটেড একটিভ চ্যাট স্টেট ট্র্যাপ (প্ল্যানিং মোড রানিং)
    # ==========================================
    if state == "PLANNING_MODE":
        reply, rem_time = generate_openrouter_chat(text, "PLANNING_MODE")
        if rem_time and context.job_queue:
            context.job_queue.run_once(scheduled_reminder_callback, when=int(rem_time)*60, chat_id=update.effective_chat.id)
        footer = get_clean_footer("PLANNING_MODE")
        return await update.message.reply_text(reply + footer, reply_markup=get_remove_keyboard())

    elif state == "PLANNING_LONG_TERM":
        reply, _ = generate_openrouter_chat(text, "PLANNING_LONG_TERM")
        footer = get_clean_footer("PLANNING_LONG_TERM")
        return await update.message.reply_text(reply + footer, reply_markup=get_remove_keyboard())

    # ==========================================
    # ৬. সকালের ১ম চ্যাটের ডাইনামিক গ্রিটিংস (কেবল ক্যাজুয়াল চ্যাটে ট্রিগার হবে)
    # ==========================================
    if user_data["last_interaction_date"] != today_str:
        user_data["last_interaction_date"] = today_str
        
        bd_now = get_bd_time()
        current_hour = bd_now.hour
        if 5 <= current_hour < 12:
            time_label = "সকাল (Morning)"
        elif 12 <= current_hour < 16:
            time_label = "দুপুর (Afternoon)"
        elif 16 <= current_hour < 19:
            time_label = "বিকাল (Evening)"
        elif 19 <= current_hour < 23:
            time_label = "রাত (Night)"
        else:
            time_label = "গভীর রাত (Late Night)"
            
        system_trigger_msg = f"[SYSTEM_ALERT: This is Tanvir's first interaction of the day. Greet him warmly labeled: {time_label}. Ask how he is feeling at this time and guide him to use /plan spell to schedule his goals. Keep the Kotafactory persona intact.]"
        
        reply, rem_time = generate_openrouter_chat(system_trigger_msg, "NORMAL")
        if rem_time and context.job_queue:
            context.job_queue.run_once(scheduled_reminder_callback, when=int(rem_time)*60, chat_id=update.effective_chat.id)
        footer = get_clean_footer("NORMAL")
        return await update.message.reply_text(reply + footer, reply_markup=get_remove_keyboard())

    # ==========================================
    # ৭. ক্যাজুয়াল চ্যাট হ্যান্ডলিং
    # ==========================================
    reply, rem_time = generate_openrouter_chat(text, "NORMAL")
    if rem_time and context.job_queue:
        context.job_queue.run_once(scheduled_reminder_callback, when=int(rem_time)*60, chat_id=update.effective_chat.id)
    footer = get_clean_footer("NORMAL")
    await update.message.reply_text(reply + footer, reply_markup=get_remove_keyboard())

# ===================================================
# BLOCK 9: HOURLY CHECK-INS & SPECIAL COMMANDS (V9.1)
# ===================================================
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    if user_data["daily_target_raw"] == "No target set yet." or "successful" in user_data["daily_target_raw"].lower(): 
        return
    current_hour = get_bd_time().hour
    if current_hour >= 0 and current_hour < 7: 
        return
    
    reply, _ = generate_openrouter_chat("[SYSTEM_TRIGGER: HOURLY SCHEDULE CHECK]", "NORMAL")
    footer = get_clean_footer("NORMAL")
    try: 
        await context.bot.send_message(chat_id=ALLOWED_CHAT_ID, text=reply + footer)
    except Exception: pass

def chapter_sort_key(item):
    key, _ = item
    match = re.match(r"([PCMB])([12])_C(\d+)", key)
    if match:
        sub, paper, ch_num = match.groups()
        return (sub, int(paper), int(ch_num))
    return (key, 0, 0)

async def chapters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    
    filter_arg = context.args[0].upper() if context.args else None
    if filter_arg and filter_arg not in ["P", "C", "M", "B"]:
        await update.message.reply_text("ভুল সাবজেক্ট কোড! শুধু P (Physics), C (Chemistry), M (Math), বা B (Biology) ব্যবহার কর ভাই।")
        return
        
    msg = "📖 সিলেবাস কোড ডিকশনারী ম্যাপ\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    current_sub = ""
    for k, v in sorted(CHAPTER_NAMES.items(), key=chapter_sort_key):
        sub_prefix = k.split("_")[0] 
        sub_letter = sub_prefix[0]   
        
        if filter_arg and sub_letter != filter_arg:
            continue
            
        if sub_prefix != current_sub:
            current_sub = sub_prefix
            msg += f"\n{SUBJECT_ICONS.get(current_sub[0], '📚')} {SUBJECT_NAMES.get(current_sub[0], current_sub)} ({current_sub})\n"
        msg += f"  • {k} -> {v}\n"
        
    await update.message.reply_text(msg)
    
# =============================================
# BLOCK 10: ENGINE RUNNER & PORT BINDERS (V10)
# =============================================
def run_dummy_server(): 
    HTTPServer(('', int(os.environ.get("PORT", 8080))), SimpleHTTPRequestHandler).serve_forever()

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    load_from_google_sheet(sync_history=True)
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # ৩টি বেসিক রুট কমান্ড রাখা হলো, বাকি সব হ্যান্ডলিং handle_message দিয়ে প্রসেসড হবে
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))  
    app.add_handler(CommandHandler("status", status_command))  
    
    # সমস্ত চ্যাট ইনপুট মেসেজ হ্যান্ডলার দিয়ে রাউট হবে
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    if app.job_queue: 
        app.job_queue.run_repeating(hourly_mentor_check, interval=3600, first=3600, name="hourly_tracker")
    
    print("✅ Jeetu Bhaiya V10 (Stable Release) successfully initiated on background threads!")
    app.run_polling()

if __name__ == '__main__': 
    main()
