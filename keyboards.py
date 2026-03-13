from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from database import get_all_channels

def get_owner_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Stats"), KeyboardButton("📢 Broadcast")],
        [KeyboardButton("🖼️ Add Pics"), KeyboardButton("🎭 Add Stickers")],
        [KeyboardButton("📸 View Pics"), KeyboardButton("🎪 View Stickers")],
        [KeyboardButton("🚫 Block User"), KeyboardButton("✅ Unblock User")],
        [KeyboardButton("➕ Add Admin"), KeyboardButton("➖ Remove Admin")],
        [KeyboardButton("📺 Add Channel"), KeyboardButton("❌ Remove Channel")],
        [KeyboardButton("🗑️ Clear Msgs"), KeyboardButton("🧹 Wipe All")],
    ], resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Stats"), KeyboardButton("📢 Broadcast")],
        [KeyboardButton("🖼️ Add Pics"), KeyboardButton("🎭 Add Stickers")],
        [KeyboardButton("📸 View Pics"), KeyboardButton("🎪 View Stickers")],
        [KeyboardButton("🚫 Block User"), KeyboardButton("✅ Unblock User")],
    ], resize_keyboard=True)

def get_user_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🗑️ Clear My Data")],
        [KeyboardButton("Buy Plan 💎")],
    ], resize_keyboard=True)

async def get_channel_buttons():
    channels = await get_all_channels()
    if not channels:
        return None
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(f"💫 {ch['name']}", url=ch['link'])])
    buttons.append([InlineKeyboardButton("✅ Check Joined", callback_data="check_join")])
    return InlineKeyboardMarkup(buttons)

def get_confirmation_keyboard(action: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes", callback_data=f"confirm_{action}"),
            InlineKeyboardButton("❌ No", callback_data="cancel_action")
        ]
    ])

def get_plans_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Buy 💎", callback_data="plan_buy"),
            InlineKeyboardButton("Cancel ❌", callback_data="plan_cancel")
        ]
    ])

def get_contact_owner_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Contact Owner", url="https://t.me/YorichiiPrime")]
    ])