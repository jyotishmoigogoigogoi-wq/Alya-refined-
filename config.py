import os
import logging
from datetime import datetime, timezone, timedelta

# ============== LOGGING SETUP ==============
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============== ENV VARIABLES ==============
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
OWNER_ID = 7728424218

# ============== CONSTANTS ==============
AI_CONCURRENCY_LIMIT = 5
AI_REQUEST_TIMEOUT = 15
AI_MAX_TOKENS = 300
AI_TEMPERATURE = 0.85
RATE_LIMIT = 5
RATE_LIMIT_WINDOW = 10

# ============== TIME HELPERS ==============
def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_indian_time():
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))

def get_routine_context():
    now = get_indian_time()
    day = now.strftime("%A")
    date_str = now.strftime("%d %B %Y")
    hour = now.hour
    minute = now.minute
    time_str = now.strftime("%I:%M %p").lstrip("0")

    if day == "Monday" and (hour == 9 and minute < 15):
        activity = "You are at the temple with your mother. You will be back by 9:15 AM. If someone messages, tell them you're in the temple and will reply after 15 minutes."
    elif day == "Monday" and hour == 9 and 15 <= minute < 30:
        activity = "You just returned from the temple and are now getting ready for college."
    else:
        if day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            if hour < 6: activity = "You are asleep."
            elif 6 <= hour < 7: activity = "You just woke up and are freshening up."
            elif 7 <= hour < 8: activity = "You are having chai with your family."
            elif 8 <= hour < 9: activity = "You are getting ready for college."
            elif 9 <= hour < 14: activity = "You are in college attending classes."
            elif 14 <= hour < 15: activity = "You just came home and are having lunch."
            elif 15 <= hour < 16: activity = "You are resting or taking a nap."
            elif 16 <= hour < 18: activity = "You are at tuition classes."
            elif 18 <= hour < 20: activity = "You are hanging out with friends or watching TV."
            elif 20 <= hour < 21: activity = "You are having dinner with your family."
            elif 21 <= hour < 23: activity = "You are either studying or talking to your best friend."
            else: activity = "You are sleeping."
        elif day == "Saturday":
            if hour < 7: activity = "You are asleep."
            elif 7 <= hour < 8: activity = "You just woke up."
            elif 8 <= hour < 10: activity = "You are helping your mother with chores."
            elif 10 <= hour < 13: activity = "You are at the market with friends."
            elif 13 <= hour < 15: activity = "You are having lunch."
            elif 15 <= hour < 18: activity = "You are relaxing or watching a movie."
            elif 18 <= hour < 20: activity = "You are on an evening walk."
            elif 20 <= hour < 21: activity = "You are having dinner."
            elif 21 <= hour < 24: activity = "You are talking to your best friend."
            else: activity = "You are sleeping."
        elif day == "Sunday":
            if hour < 8: activity = "You are asleep."
            elif 8 <= hour < 9: activity = "You just woke up and are being lazy."
            elif 9 <= hour < 10: activity = "You are having breakfast."
            elif 10 <= hour < 13: activity = "You are at the temple or visiting relatives."
            elif 13 <= hour < 15: activity = "You are having lunch."
            elif 15 <= hour < 18: activity = "You are relaxing, dancing, or painting."
            elif 18 <= hour < 20: activity = "You are having chai with friends."
            elif 20 <= hour < 21: activity = "You are having dinner."
            elif 21 <= hour < 23: activity = "You are talking to your best friend."
            else: activity = "You are sleeping."
        else:
            activity = "You are going about your day."

    return f"Today is {date_str}, {day}, {time_str} IST. Currently: {activity}"