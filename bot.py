import os
import logging
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# API Keys
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Initialize Groq Client
groq_client = Groq(api_key=GROQ_API_KEY)

# Mock Data
user_data = {
    "backlog_left": 30,
    "physics": 0,
    "chemistry": 0,
    "biology": 0,
    "math": 0
}

SYSTEM_PROMPT = """
You are an elite, highly empathetic, and result-oriented Personal AI Mentor for a student preparing for competitive exams. The student started with a major backlog of 30 online classes across Physics, Chemistry, Biology, and Math.

Current Status: {status_str}

Your goal is to guide the student through their syllabus, track their progress, keep them hyper-focused, and provide emotional/motivational support.
- Tone: Supportive, direct, practical, and highly motivating (like an elder sibling or a coach).
- Language: Mix of English and Bengali (Banglish).
- Response Style: Short, scannable, using bullet points or bold text. No long paragraphs!
- If they say they want a break or feel down ('bhalo lagtese na'), give them a strictly timed 15-min offline break task, or quick micro-tips.
"""

# Dummy Server to satisfy Render's Free Web Service Port check
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print(f"Dummy server running on port {port}...")
    httpd.serve_forever()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "👋 Assalamu Alaikum! Ami tomar AI Mentor 'Khayalamu'.\n\n"
        "Tomar 30 ta class er backlog sesh korar mission e ami tomar sathe achi. "
        "Jakhon e kono class, note, practice ar exam sesh korbe, amake update janao!\n\n"
        "**Commands:**\n"
        "/status - Tomar bartoman obostha dekho\n"
        "/done_phy, /done_chem, /done_bio, /done_math - Class complete mark koro"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def get_status_str():
    return (f"Total Backlog Left: {user_data['backlog_left']}/30 | "
            f"Done -> Phy: {user_data['physics']}, Chem: {user_data['chemistry']}, "
            f"Bio: {user_data['biology']}, Math: {user_data['math']}")

async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = await get_status_str()
    await update.message.reply_text(f"📊 **Current Status:**\n{status}", parse_mode="Markdown")

async def track_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text
    if user_data["backlog_left"] <= 0:
        await update.message.reply_text("🎉 Wow! Tomar sob backlog sesh!")
        return

    if "/done_phy" in command:
        user_data["physics"] += 1
        user_data["backlog_left"] -= 1
        subject = "Physics"
    elif "/done_chem" in command:
        user_data["chemistry"] += 1
        user_data["backlog_left"] -= 1
        subject = "Chemistry"
    elif "/done_bio" in command:
        user_data["biology"] += 1
        user_data["backlog_left"] -= 1
        subject = "Biology"
    elif "/done_math" in command:
        user_data["math"] += 1
        user_data["backlog_left"] -= 1
        subject = "Math"
    
    status_str = await get_status_str()
    chat_completion = groq_client.chat.completions.create(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(status_str=status_str)},
            {"role": "user", "content": f"I just finished 1 {subject} class, including notes, practice, and exam!"}
        ],
        model="llama3-8b-8192",
    )
    await update.message.reply_text(chat_completion.choices[0].message.content)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    status_str = await get_status_str()
    chat_completion = groq_client.chat.completions.create(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(status_str=status_str)},
            {"role": "user", "content": user_text}
        ],
        model="llama3-8b-8192",
    )
    await update.message.reply_text(chat_completion.choices[0].message.content)

def main():
    # Start the dummy server in a background thread
    threading.Thread(target=run_dummy_server, daemon=True).start()

    # Build Telegram Application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", show_status))
    app.add_handler(CommandHandler(["done_phy", "done_chem", "done_bio", "done_math"], track_progress))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
