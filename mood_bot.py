"""
Telegram Mood Rating Bot
------------------------
- Asks "Rate your current mood" every morning at 8:00 AM
- Also responds to /start and /mood commands
- Saves mood history to mood_log.csv
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
MORNING_HOUR = 8                    # Hour to send the morning prompt (24h, local time)
MORNING_MINUTE = 0
LOG_FILE = "mood_log.csv"

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
    "1": "I'm really sorry you're feeling that way 💙 Remember, tough moments pass. Take it one step at a time.",
    "2": "That sounds rough. Be kind to yourself today 🫂",
    "3": "A meh day — totally valid. Maybe something small can lift it a bit? ☕",
    "4": "Okay is good enough! Steady as she goes 🚢",
    "5": "Fine is underrated 🙂 Hope your day gets even better!",
    "6": "Good vibes! Keep it going 😊",
    "7": "Great mood — love to hear it! 🌟",
    "8": "AMAZING! Share that energy with the world 🤩✨",
}

# ── Keyboard ──────────────────────────────────────────────────────────────────
def build_keyboard() -> InlineKeyboardMarkup:
    """Build a 2-column inline keyboard of mood options."""
    buttons = [
        InlineKeyboardButton(label, callback_data=f"mood:{value}")
        for label, value in MOODS
    ]
    # Arrange in rows of 2
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

# ── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Hi! I'm your *Mood Bot*.\n\n"
        "Every morning I'll check in on how you're feeling.\n"
        "You can also type /mood anytime to rate your mood now!\n\n"
        "Let's start — how are you feeling right now?",
        parse_mode="Markdown",
        reply_markup=build_keyboard(),
    )

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🌡️ *Rate your current mood:*",
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
    # bot_data["users"] is populated whenever someone chats with the bot
    users: set = context.bot_data.get("users", set())
    for chat_id in users:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="☀️ *Good morning!*\n\nHow are you feeling today?",
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

    # Register user-tracking middleware on every update
    app.add_handler(CommandHandler("start", start), group=-1)
    app.add_handler(CommandHandler("start", track_user), group=-1)
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("mood", track_user))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Schedule the daily morning message
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