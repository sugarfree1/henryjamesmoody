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

RESPONSES = {
    "1": "This is the part where most people reach for a drink. I say reach for something better — though I'm hardly one to talk. Hang in there, kid. 🥃",
    "2": "Life's a cruel mistress. She'll chew you up, spit you out, and somehow you'll still find yourself crawling back. It gets better. Probably.",
    "3": "Meh. The official state of modern existence. At least you're honest about it — that puts you ahead of ninety percent of the population.",
    "4": "Okay. Not the stuff of great literature, but not a tragedy either. I've written worse endings. 🚬",
    "5": "Fine is the most underrated word in the English language. The world was built by people who were just fine and showed up anyway.",
    "6": "Good. Hold onto that. The universe has a sick sense of humor and won't let it last forever — so enjoy it while it's here. 😏",
    "7": "Great? Look at you, you magnificent bastard. Don't waste it — do something worthy of the feeling.",
    "8": "Amazing. I don't say this often, but I'm genuinely jealous. Go write something, call someone you love, or just sit with it. You've earned it. ✨",
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
        "So. How are you feeling right now?",
        parse_mode="Markdown",
        reply_markup=build_keyboard(),
    )

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🌡️ *Talk to me. How's the soul holding up?*",
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
    response = RESPONSES.get(score, "Thanks for sharing! 💙")

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
                text="🌅 *Another day, another chance to get it right.*\n\nHow are you feeling this fine morning, you beautiful disaster?",
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