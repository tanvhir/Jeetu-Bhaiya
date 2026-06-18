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

# Memory State Machine - V10
user_data = {
    "daily_target_raw": "No target set yet.",
    "current_state": "NORMAL", # STATES: NORMAL, STATE_SYLLABUS_MENU, MORNING_CHECKIN, PLANNING_MODE, PLANNING_LONG_TERM, WAITING_FOR_TARGET_UPDATE, WAITING_FOR_KAIZEN, WAITING_FOR_KAIZEN_UPDATE, WAITING_FOR_ADD, WAITING_FOR_CLASS, WAITING_FOR_NOTE, WAITING_FOR_PRACTICE, WAITING_FOR_EXAM
    "chat_history": [],
    "kaizen_goals": "কোনো কাইজেন প্ল্যান সেট করা হয়নি।",
    "long_term_plan": "কোনো দীর্ঘমেয়াদী প্ল্যান সেট করা হয়নি।",
    "kaizen_logs": [],
    "last_interaction_date": ""  # দিনের প্রথম মেসেজ ডিটেক্ট করার জন্য
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
    "C1_C1": "ল্যাবরেটরির নিরাপদ ব্যবহার", "C1_C2": "গুনগত রসায়ন", "C1_C3": "মৌলের পর্যায়বৃত্ত ধর্ম ও রাসায়নিক বন্ধন", "C1_C4": "রাসায়নিক পরিবর্তন", "C1_C5": "কর্মমুখী রসায়ন",
    "C2_C1": "পরিবেশ রসায়ন", "C2_C2": "জৈব রসায়ন", "C2_C3": "পরিমাণগত রসায়ন", "C2_C4": "তড়িৎ রসায়ন", "C2_C5": "অর্থনৈতিক রসায়ন",

    # 📐 MATH (M1 & M2)
    "M1_C1": "ম্যাট্রিক্স ও নির্ণায়ক", "M1_C2": "সরলরেখা", "M1_C3": "বৃত্ত", "M1_C4": "বিন্যাস ও সমাবেশ", "M1_C5": "ত্রিকোণমিতিক অনুপাত",
    "M1_C6": "সংযুক্ত কোণের ত্রিকোণমিতিক অনুপাত", "M1_C7": "ফাংশন ও ফাংশনের লেখচিত্র", "M1_C8": "বিপরীত ত্রিকোণমিতিক ফাংশন", "M1_C9": "অন্তরীকরণ", "M1_C10": "যোগজীকরণ",
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
📖 জিতু ভাইয়া AI V10 - কমান্ড ও স্পেল বুক (Spells Dictionary)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
কিবোর্ডের বাটনগুলো ছাড়াও যেকোনো সময় চ্যাটে এই বিশেষ স্পেলগুলো লিখে ভাইয়াকে কমান্ড দিতে পারিস:

💡 লং-টার্ম প্ল্যানিং স্পেল:
• /goal <আপনার বার্তা>
(যেমন: /goal ভাইয়া অর্গানিক কেমিস্ট্রির ব্যাকলগ শেষ করতে চাই)
👉 অ্যাকশন: সিলেবাসের সম্পূর্ণ র-ডেটা লোড হবে এবং ভাইয়ার সাথে দীর্ঘমেয়াদী রোডম্যাপ তৈরি হবে।

📅 শর্ট-টার্ম/ডেইলি প্ল্যানিং স্পেল:
• /plan <আপনার বার্তা>
(যেমন: /plan আজকে ২টা লেকচার করব ২ ঘণ্টায়)
👉 অ্যাকশন: সিলেবাস ও রিভিশন হিস্ট্রি লোড হবে এবং দিন/ঘণ্টা অনুযায়ী রুটিন সাজাবে।

📊 স্ট্যাটাস ও ভিজ্যুয়াল রিপোর্ট স্পেল:
• /status : সিলেবাস প্রগ্রেস, রোডম্যাপ, একটিভ টার্গেট এবং কাইজেনের ড্যাশবোর্ড দেখা।
• /report : ডিটেইল সিলেবাসের ভিজ্যুয়াল ট্রি বা ডেকোরেটেড রিপোর্ট দেখা।
• /chapters : সিলেবাস কোড ডিকশনারি ম্যাপ দেখা। (যেমন: /chapters P দিলে শুধু ফিজিক্সের চ্যাপ্টার কোড দেখাবে)।

☕ ব্রেক ও ডাইনামিক টাইমার স্পেল:
• /break <মিনিট> : নির্দিষ্ট সময় ব্রেক নেওয়া (যেমন: /break 15 দিলে ১৫ মিনিট পর ভাইয়া ডেকে আনবে)।

🔙 মেইন কিবোর্ডে ফিরে যেতে চাইলে চ্যাটে 'Back to Main Menu' বাটন চাপবি।
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ==========================================
# BLOCK 2: SYSTEM PROMPT ENGINE (V10 CASUAL/HUMAN PERSONA)
# ==========================================
SYSTEM_PROMPT_BASE = """
You are 'Jeetu Bhaiya', an elite, deeply empathetic, hardcore, and practical personal AI Mentor for a Bangladeshi second-timer varsity admission candidate.

CORE PROFILE INFO & CONTEXT:
- Target Exam: Varsity Admission 2026.
- User Status: Second Timer (Zero room for fake motivation, needs systematic planning).
- Current Long-term Road-map: {long_term_plan}
- User's Custom Kaizen Habits: {kaizen_goals}
- Recent Kaizen History Logs: {kaizen_logs_raw}
- Dynamic Study Summary: {dynamic_summary_context}

DYNAMIC TEMPERAMENTS & RULES:
1. Speak in NATURAL, CASUAL BANGLADESHI BENGALI (Use informal words like: 'তুই', 'ভাই', 'প্যারা', 'চিল', 'খেলা হবে', 'পড়ালেখা', 'বাহানা').
2. NEVER use markdown formats like asterisks (**) or hashes (#). Keep it clean and human.
3. Be short, direct and highly context-aware (3-5 lines max). No long essay lists unless in master planning mode.
4. Adapt your mood based on user progress:
   - If they are skipping targets/failing, show 'Tough Love' (be strict, say "বাহানা বাদ দিবি").
   - If they are succeeding, show immense pride.
   - If they feel down, become an emotional older brother ("প্যারা নাই ভাই, ঘুরে আয় একটু").

CONTEXT WINDOW:
- Current Bangladesh Time: {current_time}
- Today's Target/Schedule: {daily_target_raw}
"""

def get_bd_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=6)

# ==========================================
# BLOCK 3: GOOGLE SHEETS API SYNC & CONNECTORS (V10 - MEMORY PROTECTED)
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
                # বাটন ক্লিকে চলমান হিস্ট্রি যাতে ওভাররাইট না হয় তার সুরক্ষা
                if sync_history:
                    user_data["chat_history"] = data.get("chat_history", [])
                logging.info("✅ V10 Core Synchronization Complete.")
    except Exception as e: logging.error(f"Sheet Loading Error: {e}")

# ==========================================
# BLOCK 4: REVISION & BACKLOG ANALYTICS (SPACED REPETITION)
# ==========================================
def calculate_revision_and_backlogs():
    """১, ৩ ও ৭ দিন আগের শেষ করা পড়াগুলো চিহ্নিত করে রিভিশন অ্যালগরিদম সাজানো"""
    tot_lec = len(user_lectures)
    done_lec = sum(1 for v in user_lectures.values() if isinstance(v, dict) and v.get("status") == "Done")
    backlogs = tot_lec - done_lec
    
    # স্পেসড রিভিশন চেক
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
    
    # প্ল্যানিং মোডে এআইকে সম্পূর্ণ র-সিলেবাস ডেটা পাঠিয়ে দেওয়া হচ্ছে
    if context_reason in ["PLANNING_MODE", "PLANNING_LONG_TERM"]:
        full_report = generate_raw_syllabus_report_text()
        summary = f"ইউজারের লাইভ র-সিলেবাস ডেটা রিপোর্ট:\n{full_report}\n"
        summary += f"টোটাল ব্যাকলগ লেকচার সংখ্যা: {backlogs}টি।\n"
        if revs:
            summary += f"স্পেসড রিভিশনের জন্য ডিউ টপিকসমূহ: {', '.join(revs)}।"
        return summary
    else:
        # সাধারণ চ্যাটের জন্য শুধু শর্ট সামারি টোকেন বাঁচাবে
        summary = f"ব্যাকলগ লেকচার সংখ্যা: {backlogs}টি। "
        if revs:
            summary += f"আজকে বৈজ্ঞানিক রিভিশনের জন্য উপযুক্ত টপিক: {', '.join(revs[:2])}।"
        else:
            summary += "নতুন কোনো রিভিশন ডিউ নেই।"
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
# BLOCK 5: ADAPTIVE GOOGLE GENAI COGNITIVE PIPELINE (V10 - TIMEOUT, RETRY & FALLBACK)
# ==========================================
def generate_openrouter_chat(user_message: str, context_reason: str = "NORMAL") -> tuple:
    import time  # রিট্রাইয়ের মাঝে বিরতির জন্য লোকাল ইমপোর্ট
    global client
    if not client:
        if GEMINI_API_KEY:
            try: client = genai.Client(api_key=GEMINI_API_KEY)
            except Exception as e: return f"গুগল ক্লায়েন্ট এপিআই সংযোগ ত্রুটি: {str(e)[:120]}", None
        else: return "API Key Missing!", None
    
    # কন্টেক্সট অনুযায়ী র-ডেটা অথবা শর্ট সামারি ডাইনামিকালি লোড হবে
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
        logging.error(f"Prompt formatting failed: {fe}. Falling back to safe replacement.")
        system_prompt = SYSTEM_PROMPT_BASE.replace("{current_time}", get_bd_time().strftime("%I:%M %p")) \
                                            .replace("{daily_target_raw}", str(user_data["daily_target_raw"])) \
                                            .replace("{kaizen_goals}", str(user_data["kaizen_goals"])) \
                                            .replace("{long_term_plan}", str(user_data["long_term_plan"])) \
                                            .replace("{kaizen_logs_raw}", json.dumps(user_data["kaizen_logs"][:4])) \
                                            .replace("{dynamic_summary_context}", str(dynamic_context))

    # কন্টেক্সট ভিত্তিক রেসপন্স লেন্থ এবং ট্যাগ কন্ট্রোল (ডাইনামিক রেসপন্স লেন্থ)
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

    # মেমোরি স্ট্রাকচার ম্যাপিং
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

    bot_reply = None
    max_retries = 3
    retry_delay = 1.0  # সেকেন্ড
    
    # এপিআই রিট্রাই এবং প্রোডাকশন ফলব্যাক লজিক
    for attempt in range(max_retries):
        try:
            logging.info(f"⚡ Requesting Google AI Studio via: {GEMINI_MODEL} (Attempt {attempt+1}/{max_retries}, Temp: {temp})")
            
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=formatted_contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temp,
                    # ২০ সেকেন্ডের টাইমআউট যুক্ত করা হলো (ঝুলে থাকা প্রতিরোধ করতে)
                    http_options=types.HttpOptions(timeout=20000)
                )
            )
            
            bot_reply = response.text
            if bot_reply:
                break
            else:
                raise ValueError("Empty response received from API.")
                
        except Exception as e:
            logging.warning(f"⚠️ Attempt {attempt+1} failed with error: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff retry
            else:
                # ৩ বার রিট্রাই ফেইল করলে ব্যাকগ্রাউন্ডে gemini-3.1-flash-lite এ ফলব্যাক করা হবে
                FALLBACK_MODEL = "gemini-3.1-flash-lite"
                logging.info(f"🔄 Switching to fallback production model: {FALLBACK_MODEL}")
                try:
                    response = client.models.generate_content(
                        model=FALLBACK_MODEL,
                        contents=formatted_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=temp,
                            # ফলব্যাক মডেলেও ২০ সেকেন্ডের টাইমআউট প্রটেকশন
                            http_options=types.HttpOptions(timeout=20000)
                        )
                    )
                    bot_reply = response.text
                    if bot_reply:
                        break
                except Exception as fallback_err:
                    logging.error(f"❌ Fallback model also failed: {fallback_err}")
                    return f"নেটওয়ার্ক ড্রপ খাইছে ভাই! গুগল এআই এরর: {str(e)[:120]}", None

    try:
        # XML ট্যাগ পার্সিং এবং ডাটাবেজ আপডেট
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

        # সময়ের রিমাইন্ডার ডিটেক্টর
        match_rem = re.search(r"<SET_REMINDER>(\d+)</SET_REMINDER>", bot_reply, re.IGNORECASE)
        if match_rem:
            bot_reply = re.sub(r"<SET_REMINDER>\d+</SET_REMINDER>", "", bot_reply, flags=re.IGNORECASE).strip()

        # মেটাডেটা ফুটার সংযুক্তি (কনটেক্সট এটাচমেন্ট ইন্ডিকেটর)
        footer = "\n\n📂 Context Attached:\n"
        if context_reason in ["PLANNING_MODE", "PLANNING_LONG_TERM"]:
            footer += "• 📊 Detailed Syllabus Data (Raw Tree Attached)\n"
            if context_reason == "PLANNING_MODE":
                footer += "• 🔄 Spaced Revision History Loaded\n"
        else:
            footer += "• 📈 Syllabus Progress Summary Only\n"
        footer += f"• 🎯 Active Target: {user_data['daily_target_raw']}\n"
        footer += f"• 🚀 Long-term Roadmap: {'Active' if user_data['long_term_plan'] != 'কোনো দীর্ঘমেয়াদী প্ল্যান সেট করা হয়নি।' else 'None'}"
        
        bot_reply += footer
        bot_reply = bot_reply.replace("**", "").replace("#", "").strip()
        
        user_data["chat_history"].extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": bot_reply}])
        if len(user_data["chat_history"]) > MAX_HISTORY_LENGTH: 
            user_data["chat_history"] = user_data["chat_history"][-MAX_HISTORY_LENGTH:]
        
        threading.Thread(target=save_memory_to_sheet, daemon=True).start()
        return bot_reply, match_rem.group(1) if match_rem else None
            
    except Exception as e:
        logging.error(f"⚠️ API Exception: {e}")
        return f"নেটওয়ার্ক ড্রপ খাইছে ভাই! গুগল এআই এরর: {str(e)
    

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

# ==========================================
# BLOCK 7: STATIC MAIN KEYBOARD MENU
# ==========================================
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        ['Check Status', 'প্লানিং মোড', 'লং-টার্ম গোল সেট'],
        ['Update Target', 'Manage Kaizen', 'Update Kaizen'],
        ['Manage Syllabus', 'Syllabus Report']
    ], resize_keyboard=True)

def get_syllabus_keyboard():
    return ReplyKeyboardMarkup([
        ['Add New Lecture', 'Mark Class Done'],
        ['Mark Note Done', 'Mark Practice Done', 'Mark Exam Done'],
        ['Back to Main Menu']
    ], resize_keyboard=True)

# ==========================================
# BLOCK 8: MESSAGE PROCESSOR & STATE CONTROLLER (V10 - DYNAMIC SPELL ROUTED)
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    user_data["current_state"] = "NORMAL"
    msg = "কিরে ভাই, আমি তোর মেন্টর জিতু ভাইয়া। V10 প্রো মাস্টার সংস্করণ সাকসেসফুলি রানিং! পড়াশোনার কি অবস্থা বল?\n"
    msg += HELP_TEXT
    await update.message.reply_text(msg, reply_markup=get_main_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    await update.message.reply_text(HELP_TEXT)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    await update.message.reply_text(await generate_premium_status())

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    await view_syllabus_tree(update, context)

async def scheduled_reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    """ডাইনামিক রিমাইন্ডারের ওয়ান-টাইম ফলো-আপ ট্রিগার"""
    job = context.job
    try:
        await context.bot.send_message(chat_id=job.chat_id, text="কিরে! ব্রেক শেষ বলছিলি না? সময় শেষ, চল এবার জলদি পড়ার টেবিলে ফেরা যাক।")
    except Exception as e:
        logging.error(f"Failed to send scheduler follow-up: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    text = update.message.text.strip()
    state = user_data["current_state"]

    # --- ১. স্পেল/কমান্ড ডিটেক্টর ইঞ্জিন (Natural Language Command Trigger) ---
    if text.startswith("/goal"):
        user_msg = text[5:].strip()
        if not user_msg:
            return await update.message.reply_text("💡 ভাই, /goal স্পেলের সাথে আপনার রোডম্যাপের বার্তাটি দিন। যেমন: /goal ভাইয়া একটা মাস্টার প্ল্যান দাও")
        user_data["current_state"] = "PLANNING_LONG_TERM"
        load_from_google_sheet(sync_history=False)
        reply, _ = generate_openrouter_chat(user_msg, "PLANNING_LONG_TERM")
        return await update.message.reply_text(reply)
        
    elif text.startswith("/plan"):
        user_msg = text[5:].strip()
        if not user_msg:
            return await update.message.reply_text("📅 ভাই, /plan স্পেলের সাথে আপনার মেসেজটি দিন। যেমন: /plan আজকে ২টা লেকচার শেষ করব")
        user_data["current_state"] = "PLANNING_MODE"
        load_from_google_sheet(sync_history=False)
        reply, rem_time = generate_openrouter_chat(user_msg, "PLANNING_MODE")
        if rem_time and context.job_queue:
            context.job_queue.run_once(scheduled_reminder_callback, when=int(rem_time)*60, chat_id=update.effective_chat.id)
        return await update.message.reply_text(reply)
        
    elif text.startswith("/break"):
        parts = text.split()
        if len(parts) > 1 and parts[1].isdigit():
            minutes = int(parts[1])
            if context.job_queue:
                context.job_queue.run_once(scheduled_reminder_callback, when=minutes*60, chat_id=update.effective_chat.id)
            return await update.message.reply_text(f"☕ ঠিক আছে ভাই, যা একটু রিল্যাক্স কর। ঠিক {minutes} মিনিট পর আমি তোকে ডেকে পড়ার টেবিলে ফিরিয়ে আনব।")
        else:
            return await update.message.reply_text("⚠️ ভুল ফরম্যাট! সঠিক ফরম্যাট: /break 15 (১৫ মিনিটের ব্রেক)")

    # --- ২. সকালের ফাস্ট মেসেজ ডিটেকশন (সম্পূর্ণ ডাইনামিক ও এআই-ভিত্তিক গ্রিটিং) ---
    today_str = get_bd_time().strftime("%Y-%m-%d")
    if user_data["last_interaction_date"] != today_str:
        user_data["last_interaction_date"] = today_str
        # প্রথম মেসেজেই এআই নিজে থেকে বাংলা গ্রিটিং জেনারেট করবে যা হিস্ট্রিতেও সেভ থাকবে
        reply, rem_time = generate_openrouter_chat("[SYSTEM_ALERT: This is the user's first interaction today. Greet them warmly and casually in Bengali, ask if they are ready/fresh, and encourage them to use the /plan spell or click 'Planning Mode' to schedule today's mission.]", "NORMAL")
        if rem_time and context.job_queue:
            context.job_queue.run_once(scheduled_reminder_callback, when=int(rem_time)*60, chat_id=update.effective_chat.id)
        return await update.message.reply_text(reply, reply_markup=get_main_keyboard())

    # --- ৩. গ্লোবাল মেনু বাটন নেভিগেশন ---
    if text == 'Check Status': 
        return await update.message.reply_text(await generate_premium_status())
    elif text == 'Syllabus Report': 
        return await view_syllabus_tree(update, context)
    elif text == 'Manage Syllabus': 
        user_data["current_state"] = "STATE_SYLLABUS_MENU"
        return await update.message.reply_text("সিলেবাস কনফিগারেশন মোড সচল করা হয়েছে:", reply_markup=get_syllabus_keyboard())
    elif text == 'Back to Main Menu': 
        user_data["current_state"] = "NORMAL"
        return await update.message.reply_text("🔙 মূল মেনু", reply_markup=get_main_keyboard())
    
    elif text == 'প্লানিং মোড': 
        user_data["current_state"] = "PLANNING_MODE"
        # সিলেবাস সিঙ্ক হবে কিন্তু রানিং চ্যাট হিস্ট্রি মুছে যাবে না (sync_history=False)
        load_from_google_sheet(sync_history=False)
        msg = "তুই এখন প্লানিং মোডে আছিস। ভাইয়ার কাছে তোর পুরো সিলেবাস রিপোর্ট রেডি আছে। বল আজকে কি কি কাভার করবি আর কোনটার পেছনে কতক্ষণ সময় দিবি?"
        return await update.message.reply_text(msg)
        
    elif text == 'লং-টার্ম গোল সেট':
        user_data["current_state"] = "PLANNING_LONG_TERM"
        # সিলেবাস সিঙ্ক হবে কিন্তু রানিং চ্যাট হিস্ট্রি মুছে যাবে না (sync_history=False)
        load_from_google_sheet(sync_history=False)
        msg = "চল একটা স্ট্রং লং-টার্ম রোডম্যাপ সাজাই। তোর কোচিংয়ের বর্তমান অবস্থা কি আর কবে নাগাদ ব্যাকলগ শেষ করে ট্র্যাকে ফিরতে চাস বুঝিয়ে বল ভাইয়াকে।"
        return await update.message.reply_text(msg)

    elif text == 'Update Target': 
        user_data["current_state"] = "WAITING_FOR_TARGET_UPDATE"
        return await update.message.reply_text("তোর আজকের টার্গেটের আপডেট কি? কমপ্লিট করতে পারলি নাকি ঝুলে গেছে?")
    elif text == 'Manage Kaizen': 
        user_data["current_state"] = "WAITING_FOR_KAIZEN"
        return await update.message.reply_text("তোর নতুন লাইফস্টাইল অভ্যাসটা কী সেট করতে চাস লিখে বল।")
    elif text == 'Update Kaizen': 
        user_data["current_state"] = "WAITING_FOR_KAIZEN_UPDATE"
        return await update.message.reply_text("কালকের কাইজেন গোলটা পারলি নাকি ভেস্তে গেল?")

    # --- ৪. সাব-মেনু কমান্ডস ---
    elif text == 'Add New Lecture': 
        user_data["current_state"] = "WAITING_FOR_ADD"
        return await update.message.reply_text("কোন লেকচারটা অ্যাড করতে চাস বল? (যেমন: P1 C2 L1 বা P1 C2 L1-10)")
    elif text == 'Mark Class Done': 
        user_data["current_state"] = "WAITING_FOR_CLASS"
        return await update.message.reply_text("কোন লেকচার শেষ করলি? কোড দে (যেমন: P1 C2 L1)")
    elif text == 'Mark Note Done': 
        user_data["current_state"] = "WAITING_FOR_NOTE"
        return await update.message.reply_text("কোন চ্যাপ্টারের নোট কমপ্লিট? কোড দে (যেমন: P1 C2)")
    elif text == 'Mark Practice Done': 
        user_data["current_state"] = "WAITING_FOR_PRACTICE"
        return await update.message.reply_text("কোন চ্যাপ্টারের প্র্যাকটিস ডান? কোড দে (যেমন: P1 C2)")
    elif text == 'Mark Exam Done': 
        user_data["current_state"] = "WAITING_FOR_EXAM"
        return await update.message.reply_text("কোন চ্যাপ্টারের এক্সাম ডান? কোড দে (যেমন: P1 C2)")

    if state == "STATE_SYLLABUS_MENU":
        return await update.message.reply_text("সিলেবাস বাটনগুলো ব্যবহার কর অথবা 'Back to Main Menu' ক্লিক কর।", reply_markup=get_syllabus_keyboard())

    # --- ৫. আইসোলেটেড স্টেট ট্র্যাপ এবং সাব-স্টেট প্রসেসিং ---
    if state == "PLANNING_MODE":
        reply, rem_time = generate_openrouter_chat(text, "PLANNING_MODE")
        if rem_time and context.job_queue:
            context.job_queue.run_once(scheduled_reminder_callback, when=int(rem_time)*60, chat_id=update.effective_chat.id)
        return await update.message.reply_text(reply)

    elif state == "PLANNING_LONG_TERM":
        reply, _ = generate_openrouter_chat(text, "PLANNING_LONG_TERM")
        return await update.message.reply_text(reply)

    elif state == "WAITING_FOR_TARGET_UPDATE":
        user_data["current_state"] = "NORMAL"
        reply, _ = generate_openrouter_chat(text, "PARSING_TARGET_UPDATE")
        return await update.message.reply_text(reply, reply_markup=get_main_keyboard())

    elif state == "WAITING_FOR_KAIZEN":
        user_data["current_state"] = "NORMAL"
        reply, _ = generate_openrouter_chat(f"New Lifestyle Habit: {text}", "PARSING_KAIZEN_SET")
        return await update.message.reply_text(reply, reply_markup=get_main_keyboard())

    elif state == "WAITING_FOR_KAIZEN_UPDATE":
        user_data["current_state"] = "NORMAL"
        reply, _ = generate_openrouter_chat(text, "PARSING_KAIZEN_LOG")
        return await update.message.reply_text(reply, reply_markup=get_main_keyboard())

    # --- ৬. সিলেবাস ইন-মেমোরি প্রসেসর (বাল্ক মাল্টিপল ইনপুট কাস্টম নেম সহ) ---
    elif state == "WAITING_FOR_ADD":
        # লাইন ব্রেক অনুযায়ী ইনপুটগুলোকে আলাদা করা হচ্ছে
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        success_count = 0
        success_messages = []
        errors = []
        
        for line in lines:
            mode, ch_key, lec_info = parse_smart_shortcode(line)
            if not ch_key:
                errors.append(f"'{line}' -> কোড সঠিক নয়")
                continue
            
            # চ্যাপ্টারের বাংলা নাম ডিকশনারি থেকে বের করা হচ্ছে, না থাকলে কোডটাই দেখাবে
            ch_name = CHAPTER_NAMES.get(ch_key, ch_key)
            
            if ch_key not in user_chapters: 
                user_chapters[ch_key] = {"progress": "0/0", "note": "Pending", "practice": "Pending", "exam": "Pending"}
            
            if mode == "RANGE":
                start_l, end_l = lec_info
                for i in range(start_l, end_l + 1):
                    user_lectures[f"{ch_key}_L{i}"] = {"status": "Pending", "last_studied_at": ""}
                    post_lecture_to_sheet(ch_key, f"L{i}", "Pending")
                success_messages.append(f"{ch_name} চ্যাপ্টারের L{start_l} থেকে L{end_l} পর্যন্ত বাল্ক লেকচার অ্যাড করা হয়েছে!")
                success_count += 1
            elif mode == "LECTURE":
                user_lectures[f"{ch_key}_{lec_info}"] = {"status": "Pending", "last_studied_at": ""}
                post_lecture_to_sheet(ch_key, lec_info, "Pending")
                success_messages.append(f"{ch_name} চ্যাপ্টারে {lec_info} অ্যাড করা হয়েছে!")
                success_count += 1
            else:
                errors.append(f"'{line}' -> লেকচার বা রেঞ্জ কোড খুঁজে পাওয়া যায়নি")
                
        user_data["current_state"] = "STATE_SYLLABUS_MENU"
        
        reply_msg = "বাল্ক লেকচার অ্যাড প্রক্রিয়া সম্পন্ন হয়েছে!\n\n"
        if success_messages:
            reply_msg += "✅ সফলভাবে যুক্ত করা টাস্কসমূহ:\n" + "\n".join([f"  • {m}" for m in success_messages])
            
        if errors:
            reply_msg += f"\n\n❌ কিছু লাইনে সমস্যা দেখা গেছে:\n" + "\n".join([f"  • {e}" for e in errors])
            
        return await update.message.reply_text(reply_msg, reply_markup=get_syllabus_keyboard())

    elif state == "WAITING_FOR_CLASS":
        mode, ch_key, lec_key = parse_smart_shortcode(text)
        if not ch_key or mode != "LECTURE": return await update.message.reply_text("ভুল শর্টকোড! ট্রাই কর এভাবে: P1 C2 L1")
        full_lkey = f"{ch_key}_{lec_key}"
        
        today_date = get_bd_time().strftime("%Y-%m-%d")
        user_lectures[full_lkey] = {"status": "Done", "last_studied_at": today_date}
        
        tot = sum(1 for k in user_lectures.keys() if k.startswith(ch_key+"_"))
        dn = sum(1 for k, v in user_lectures.items() if k.startswith(ch_key+"_") and isinstance(v, dict) and v.get("status") == "Done")
        if ch_key in user_chapters: user_chapters[ch_key]["progress"] = f"{dn}/{tot}"
        
        post_lecture_to_sheet(ch_key, lec_key, "Done")
        user_data["current_state"] = "STATE_SYLLABUS_MENU"
        return await update.message.reply_text("লেকচার ক্লাস সফলভাবে সম্পন্ন মার্ক করা হয়েছে!", reply_markup=get_syllabus_keyboard())

    elif state in ["WAITING_FOR_NOTE", "WAITING_FOR_PRACTICE", "WAITING_FOR_EXAM"]:
        mode, ch_key, _ = parse_smart_shortcode(text)
        if not ch_key: return await update.message.reply_text("ভুল চ্যাপ্টার শর্টকোড! ট্রাই কর এভাবে: P1 C2")
        task = state.split("_")[-1].lower()
        
        if ch_key not in user_chapters: 
            user_chapters[ch_key] = {"progress": "0/0", "note": "Pending", "practice": "Pending", "exam": "Pending"}
        user_chapters[ch_key][task] = "Done"
        
        post_chapter_task_to_sheet(ch_key, task, "Done")
        user_data["current_state"] = "STATE_SYLLABUS_MENU"
        return await update.message.reply_text(f"চ্যাপ্টারের {task.capitalize()} সফলভাবে ডান মার্ক করা হয়েছে!", reply_markup=get_syllabus_keyboard())

    # --- ৭. ক্যাজুয়াল নরমাল চ্যাট হ্যান্ডলিং ---
    reply, rem_time = generate_openrouter_chat(text, "NORMAL")
    if rem_time and context.job_queue:
        context.job_queue.run_once(scheduled_reminder_callback, when=int(rem_time)*60, chat_id=update.effective_chat.id)
    await update.message.reply_text(reply)

# ===================================================
# BLOCK 9: HOURLY CHECK-INS & SPECIAL COMMANDS (V9.1)
# ===================================================
async def hourly_mentor_check(context: ContextTypes.DEFAULT_TYPE):
    """বোরিং চেক রিপ্লেসমেন্ট: শুধু কাজের টাইম স্লট বা ডেটাবেজ চেক ট্র্যাকিং"""
    if user_data["daily_target_raw"] == "No target set yet." or "successful" in user_data["daily_target_raw"].lower(): 
        return
    current_hour = get_bd_time().hour
    if current_hour >= 0 and current_hour < 7: # গভীর রাতে খোঁচা দেবে না
        return
    
    reply, _ = generate_openrouter_chat("[SYSTEM_TRIGGER: HOURLY SCHEDULE CHECK]", "NORMAL")
    try: 
        await context.bot.send_message(chat_id=ALLOWED_CHAT_ID, text=reply)
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
    
    # ইউজার কোনো প্যারামিটার দিয়েছে কি না চেক করি (যেমন: P, C, M, B)
    filter_arg = context.args[0].upper() if context.args else None
    
    # ইনপুট ভ্যালিডেশন
    if filter_arg and filter_arg not in ["P", "C", "M", "B"]:
        await update.message.reply_text("ভুল সাবজেক্ট কোড! শুধু P (Physics), C (Chemistry), M (Math), বা B (Biology) ব্যবহার কর ভাই।")
        return
        
    msg = "📖 সিলেবাস কোড ডিকশনারী ম্যাপ\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    current_sub = ""
    for k, v in sorted(CHAPTER_NAMES.items(), key=chapter_sort_key):
        sub_prefix = k.split("_")[0] # e.g., P1, C2, M1
        sub_letter = sub_prefix[0]   # e.g., P, C, M, B
        
        # ফিল্টার আর্গুমেন্ট থাকলে শুধু ম্যাচিং বিষয়ের চ্যাপ্টারগুলো দেখাবে
        if filter_arg and sub_letter != filter_arg:
            continue
            
        if sub_prefix != current_sub:
            current_sub = sub_prefix
            msg += f"\n{SUBJECT_ICONS.get(current_sub[0], '📚')} {SUBJECT_NAMES.get(current_sub[0], current_sub)} ({current_sub})\n"
        msg += f"  • {k} -> {v}\n"
        
    await update.message.reply_text(msg)
    
# ==========================================
# BLOCK 10: ENGINE RUNNER & PORT BINDERS (V10)
# ==========================================
def run_dummy_server(): 
    HTTPServer(('', int(os.environ.get("PORT", 8080))), SimpleHTTPRequestHandler).serve_forever()

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    # স্টার্টআপের সময় সম্পূর্ণ ডাটাবেজ ও হিস্ট্রি একবার ফুল সিঙ্ক করা হবে (sync_history=True)
    load_from_google_sheet(sync_history=True)
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # কমান্ড হ্যান্ডলার রেজিস্ট্রেশন
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))  # /help কমান্ড রেজিস্টার করা হলো
    app.add_handler(CommandHandler("status", status_command))  # /status কমান্ড রেজিস্টার করা হলো
    app.add_handler(CommandHandler("report", report_command))  # /report কমান্ড রেজিস্টার করা হলো
    app.add_handler(CommandHandler("chapters", chapters_command))  # /chapters কমান্ড রেজিস্টার করা হলো
    
    # মেসেজ হ্যান্ডলার রেজিস্ট্রেশন (~filters.COMMAND ফিল্টারটি উঠিয়ে নেওয়া হয়েছে যাতে /goal বা /plan চ্যাটে টাইপ করলে handle_message এ এসে সচল হয়)
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    if app.job_queue: 
        app.job_queue.run_repeating(hourly_mentor_check, interval=3600, first=3600, name="hourly_tracker")
    
    print("✅ Jeetu Bhaiya AI V10 (Production Final Engine) successfully initiated on background threads!")
    app.run_polling()

if __name__ == '__main__': 
    main()
