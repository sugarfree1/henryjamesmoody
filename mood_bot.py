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
import io
import json
import random
from datetime import datetime, time, timezone, timedelta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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

MORNING_HOUR_UTC = 7   # 8:00 AM Valencia (UTC+1 winter) — change to 6 in summer (UTC+2)
MORNING_MINUTE = 0
LOG_FILE = "/data/mood_log.csv"    # Persistent volume mounted at /data
USERS_FILE = "/data/users.json"    # Persists chat IDs across restarts

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

# ── Persistent user tracking ──────────────────────────────────────────────────
def load_users() -> set:
    if os.path.isfile(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_users(users: set) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(users), f)


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
    users: set = context.bot_data.setdefault("users", load_users())
    users.add(update.effective_chat.id)
    save_users(users)
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
    users: set = context.bot_data.setdefault("users", load_users())
    users.add(update.effective_chat.id)
    save_users(users)
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

# ── Chart generation ──────────────────────────────────────────────────────────
MOOD_LABELS = {1:"Terrible",2:"Bad",3:"Meh",4:"Okay",5:"Fine",6:"Good",7:"Great",8:"Amazing"}
MOOD_COLORS = {1:"#E24B4A",2:"#D85A30",3:"#BA7517",4:"#888780",5:"#1D9E75",6:"#378ADD",7:"#7F77DD",8:"#D4537E"}

def generate_week_chart(username: str) -> io.BytesIO | None:
    """Read CSV, filter last 7 days for username, return PNG bytes or None."""
    if not os.path.isfile(LOG_FILE):
        return None

    cutoff = datetime.now() - timedelta(days=7)
    timestamps, scores = [], []

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) < 4:
                continue
            ts_str, _, uname, score_str = row[0], row[1], row[2], row[3]
            if uname != username:
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
                score = int(score_str)
            except ValueError:
                continue
            if ts >= cutoff:
                timestamps.append(ts)
                scores.append(score)

    if not timestamps:
        return None

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    ax.plot(timestamps, scores, color="#378ADD", linewidth=2, zorder=2)
    for ts, score in zip(timestamps, scores):
        ax.scatter(ts, score, color=MOOD_COLORS.get(score, "#888780"), s=80, zorder=3)

    ax.set_ylim(0.5, 8.5)
    ax.set_yticks(range(1, 9))
    ax.set_yticklabels(
        [f"{i} · {MOOD_LABELS[i]}" for i in range(1, 9)],
        color="#aaaaaa", fontsize=9
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    plt.xticks(color="#aaaaaa", fontsize=9, rotation=30)
    ax.tick_params(axis="both", length=0)
    ax.grid(axis="y", color="#ffffff", alpha=0.07, linestyle="--")
    ax.grid(axis="x", color="#ffffff", alpha=0.04, linestyle="--")
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.set_title(f"Mood — last 7 days · @{username}", color="#dddddd", fontsize=12, pad=14)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf

async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    username = update.effective_user.username or update.effective_user.first_name
    await update.message.reply_text("📊 Generating your weekly mood chart...")
    buf = generate_week_chart(username)
    if buf is None:
        await update.message.reply_text("No mood entries found for the past 7 days. Use /mood to log some!")
        return
    await update.message.reply_photo(photo=buf, caption=f"_{random_quote('greetings')}_", parse_mode="Markdown")


async def send_morning_prompt(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by the job queue every morning — sends mood prompt to all known users."""
    users: set = load_users()
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

# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("week", week_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    job_queue = app.job_queue
    job_queue.run_daily(
        send_morning_prompt,
        time=time(hour=MORNING_HOUR_UTC, minute=MORNING_MINUTE, tzinfo=timezone.utc),
        name="morning_mood",
    )

    logger.info("Bot started. Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()