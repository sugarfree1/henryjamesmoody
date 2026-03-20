"""
Telegram Mood Rating Bot
------------------------
- Asks "Rate your current mood" every morning at 8:00 AM
- Also responds to /start and /mood commands
- Saves mood history to /data/mood_log.csv (Railway persistent volume)
"""

import logging
import csv
import os
import json
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

MORNING_HOUR = 8        # Hour to send the morning prompt (24h, local time)
MORNING_MINUTE = 0
LOG_FILE = "/data/mood_log.csv"   # Persistent volume mounted at /data

# ── Load Hank Moody quotes ────────────────────────────────────────────────────
QUOTES_FILE = os.path.join(os.path.dirname(__file__), "hank_quotes.json")
with open(QUOTES_FILE, "r", encoding="utf-8") as f:
    QUOTES = json.load(f)

def random_quote(category: str) -> str:
    return random.choice(QUOTES.get(category, ["..."]))

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Mood options ──────────────────────────────────────────────────────────────
MOODS = [
    ("😩 Terrible",  "1"),
    ("😞 Bad",       "2"),
    ("😕 Meh",       "3"),
    ("😐 Okay",      "4"),
    ("🙂 Fine",      "5"),
    ("😊 Good",      "6"),
    ("😄 Great",     "7"),
    ("🤩 Amazing",   "8"),
]

SCORE_TO_CATEGORY = {
    "1": "terrible",
    "2": "bad",
    "3": "meh",
    "4": "okay",
    "5": "fine",
    "6": "good",
    "7": "great",
    "8": "amazing",
}

# ── Keyboard ──────────────────────────────────────────────────────────────────
def build_keyboard() -> InlineKeyboardMarkup:
    """Build a 2-column inline keyboard of mood options."""
    buttons = [
        InlineKeyboardButton(label, callback_data=f"mood:{value}")
        for label, value in MOODS
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)

# ── CSV logging ───────────────────────────────────────────────────────────────
def log_mood(user_id: int, username: str, score: str) -> None:
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "user_id", "username", "mood_score"])
        writer.writerow([datetime.now().isoformat(), user_id, username, score])
    logger.info(f"Logged mood {score} for {username}")

# ── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *Hank Moody here.* Well, not really — but close enough.\n\n"
        "Every morning I'll drag myself out of whatever mess I'm in to ask how you're doing. "
        "It's the least I can do.\n\n"
        "You can also type /mood anytime — day or night, no judgment.\n\n"
        f"_{random_quote('greetings')}_",
        parse_mode="Markdown",
        reply_markup=build_keyboard(),
    )

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"🌡️ _{random_quote('greetings')}_",
        parse_mode="Markdown",
        reply_markup=build_keyboard(),
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("mood:"):
        return

    score = query.data.split(":")[1]
    user = query.from_user
    log_mood(user.id, user.username or user.first_name, score)

    label = next(l for l, v in MOODS if v == score)
    category = SCORE_TO_CATEGORY.get(score, "okay")
    response = random_quote(category)

    await query.edit_message_text(
        f"You rated your mood: *{label}*\n\n{response}",
        parse_mode="Markdown",
    )

# ── Morning job ───────────────────────────────────────────────────────────────
async def send_morning_prompt(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by the job queue every morning — sends mood prompt to all known users."""
    users: set = context.bot_data.get("users", set())
    for chat_id in users:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🌅 *{random_quote('greetings')}*",
                parse_mode="Markdown",
                reply_markup=build_keyboard(),
            )
        except Exception as e:
            logger.warning(f"Could not message {chat_id}: {e}")

# Track users who interact with the bot so we know who to message
async def track_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user:
        users: set = context.bot_data.setdefault("users", set())
        users.add(update.effective_chat.id)

# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start), group=-1)
    app.add_handler(CommandHandler("start", track_user), group=-1)
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("mood", track_user))
    app.add_handler(CallbackQueryHandler(button_callback))

    job_queue = app.job_queue
    job_queue.run_daily(
        send_morning_prompt,
        time=datetime.now().replace(
            hour=MORNING_HOUR, minute=MORNING_MINUTE, second=0, microsecond=0
        ).timetz(),
        name="morning_mood",
    )

    logger.info("Bot started. Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()