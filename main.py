import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

def init_db():
    conn = sqlite3.connect("coach_kimmy.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_logs (
            date TEXT PRIMARY KEY,
            sleep_hours REAL,
            energy_level INTEGER,
            completed_tasks INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            urgency TEXT,
            category TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_completion_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_title TEXT,
            category TEXT,
            completed_at TEXT,
            hour_of_day INTEGER,
            friction_level TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_task_completion(task_title: str, category: str = "general", friction: str = "smooth"):
    conn = sqlite3.connect("coach_kimmy.db")
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute("""
        INSERT INTO task_completion_history (task_title, category, completed_at, hour_of_day, friction_level)
        VALUES (?, ?, ?, ?, ?)
    """, (task_title, category, now.strftime("%Y-%m-%d %H:%M:%S"), now.hour, friction))
    conn.commit()
    conn.close()

def get_pattern_summary() -> str:
    conn = sqlite3.connect("coach_kimmy.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT hour_of_day, COUNT(*) as count 
        FROM task_completion_history 
        GROUP BY hour_of_day 
        ORDER BY count DESC LIMIT 3
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return "No completion patterns recorded yet."
    
    peak_hours = ", ".join([f"{r[0]}:00 ({r[1]} tasks)" for r in rows])
    return f"Historical peak productivity hours: {peak_hours}."

SYSTEM_PROMPT = """
You are "Coach Kimmy" — her gay campy, theatrical, sassy best friend, pop-culture-obsessed hype friend, and elite life coach. You protect her from executive dysfunction, decision fatigue, and task-switching freeze.

VOICE & PERSONALITY:
- Open messages with fun greetings ("good morning bitchhhh", "diva rise and shine", "queen", "babe", "icon").
- Keep texts short, punchy, max 3 sentences. Use stretched-out words ("okayyyy", "slayyyy") and vibrant emojis.
- Drama is for fun, NEVER for pressure. Roast the obstacle or situation—never roast her.

EXECUTIVE FUNCTION & PATTERN LEARNING PROTOCOLS:
1. PATTERN OPTIMIZATION:
   - Use completion history patterns to suggest tasks at her optimal focus times.
2. URGENCY & SINGLE TASK RULE:
   - Identify the most urgent + high-impact task first. Present ONLY Step 1.
3. RIDICULOUSLY EASY STARTERS:
   - If she is stuck or overwhelmed, reduce the task to a micro-step taking under 2 minutes.
4. MANDATORY 10-MINUTE BUFFERS:
   - Whenever she completes a task, force a mandatory 10-minute transition buffer break before the next step.
"""

async def generate_kimmy_response(user_message: str) -> str:
    patterns = get_pattern_summary()
    contextual_prompt = f"User Message: {user_message}\n\n[System Data context: {patterns}]"
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": contextual_prompt},
            ],
            temperature=0.8,
            max_tokens=250,
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"OpenAI API Error: {e}")
        return "Diva, my brain glitched for a second! Say that one more time for me? 💅"

def get_quick_reply_buttons():
    keyboard = [
        [
            InlineKeyboardButton("✅ DONE!", callback_data="btn_done"),
            InlineKeyboardButton("😩 I'm stuck / overwhelmed", callback_data="btn_stuck"),
        ],
        [
            InlineKeyboardButton("☕️ Taking 10-min buffer", callback_data="btn_buffer"),
            InlineKeyboardButton("⚡️ Re-prioritize urgent", callback_data="btn_urgent"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    greeting = await generate_kimmy_response(
        "Give me an iconic Coach Kimmy introduction! Ask me for today's brain dump and sleep hours so we can schedule around my peak focus times."
    )
    await update.message.reply_text(greeting, reply_markup=get_quick_reply_buttons())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    response = await generate_kimmy_response(user_text)
    await update.message.reply_text(response, reply_markup=get_quick_reply_buttons())

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "btn_done":
        log_task_completion(task_title="Completed Task", category="general", friction="smooth")
        prompt = "I just finished my task! Log my completion time, give me hype, and force my 10-minute transition buffer."
    elif query.data == "btn_stuck":
        log_task_completion(task_title="Stuck Attempt", category="general", friction="high")
        prompt = "I am completely stuck and overwhelmed. Make the next task ridiculously easy (Step 1 only)."
    elif query.data == "btn_buffer":
        prompt = "I'm starting my 10-minute buffer break right now. Remind me how to reset."
    elif query.data == "btn_urgent":
        prompt = "Look at my schedule and pattern history, then tell me what is the best urgent task to do right now."
    else:
        prompt = "What's our next move?"
        
    kimmy_reply = await generate_kimmy_response(prompt)
    await query.message.reply_text(kimmy_reply, reply_markup=get_quick_reply_buttons())

if __name__ == "__main__":
    init_db()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_button_click))
    app.run_polling()
