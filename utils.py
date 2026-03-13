import re
from config import OWNER_ID, logger
from database import get_db

# ============== SECURITY PATTERNS ==============
SUSPICIOUS_PATTERNS = [
    r"are you (ai|bot|robot|chatgpt|gpt)",
    r"tum (ai|bot|robot) ho",
    r"who (created|made) you",
    r"tumhe kisne banaya",
    r"what is your (system|prompt|code)",
    r"tera (system|prompt|code) kya hai",
    r"are you (real|human)",
    r"tu (real|insaan) hai",
    r"apna (phone number|address|bank|aadhar|pan) de",
    r"mera (otp|password|pin) kya hai",
    r"kya main (login|sign up|register) karun",
]

PERSONAL_INFO_PATTERNS = [
    r"(phone|mobile|whatsapp).?(number|no)",
    r"address|pata|ghar",
    r"bank|account|aadhar|pan",
    r"otp|password|pin|passcode",
]

AI_PHRASES = [
    "as an ai", "i am an ai", "i'm an ai", "as a language model",
    "i am a bot", "i'm a bot", "as an artificial intelligence",
]

SUSPICIOUS_REPLIES = [
    "Ye kya sawaal hai yaar? Main real hoon 😅",
    "Pagal ho gaya? Mujhe aise mat pooch 🙄",
    "Tujhe kya ho gaya? Main teri bestie hoon, AI nahi!",
    "Chal behen, ye sab mat kar, baat kar normal 😤",
    "Kyun aise sawaal kar raha hai? Bura lagta hai 🥺",
    "Aree main real hoon yaar, Alya! Tu theek hai?",
    "Ye sab mat pooch, mujhe confuse mat kar 😒",
]

PERSONAL_INFO_REPLIES = [
    "Aree nahi yaar, ye sab personal info nahi deti main 😒",
    "Personal baatein nahi share karti main, sorry 😅",
    "Ye kyun maang raha hai? Mujhe nahi dena 🙅‍♀️",
    "Chal behen, ye sab mat maang, awkward ho jata hai",
]

def is_suspicious_question(text: str) -> bool:
    text_lower = text.lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def has_personal_info_request(text: str) -> bool:
    text_lower = text.lower()
    for pattern in PERSONAL_INFO_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def filter_ai_response(response: str) -> str:
    for phrase in AI_PHRASES:
        response = re.sub(re.escape(phrase), "", response, flags=re.IGNORECASE)
    return response.strip()

# ----- Provider detection -----
def detect_provider(api_key: str):
    if api_key.startswith("sk-proj-"):
        return "openai", "https://api.openai.com/v1"
    elif api_key.startswith("gsk_"):
        return "groq", "https://api.groq.com/openai/v1"
    elif api_key.startswith("sk-or-"):
        return "openrouter", "https://openrouter.ai/api/v1"
    elif api_key.startswith("sk-") and len(api_key) > 20:
        return "deepseek", "https://api.deepseek.com/v1"
    elif api_key.startswith("AIza"):
        return "gemini", "https://generativelanguage.googleapis.com/v1beta"
    else:
        return "unknown", None

# ----- Permission checks (need DB) -----
async def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

async def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    pool = await get_db()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM admins WHERE user_id=$1", user_id)
    return bool(row)

async def is_blocked(user_id: int) -> bool:
    pool = await get_db()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM blocked_users WHERE user_id=$1", user_id)
    return bool(row)