from telegram import Update
from telegram.ext import ContextTypes
from database import upsert_user, is_joined_all_channels
from utils import is_owner, is_admin, is_blocked
from keyboards import get_owner_keyboard, get_admin_keyboard, get_user_keyboard, get_channel_buttons

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    chat_type = update.effective_chat.type
    if chat_type in ("group", "supergroup"):
        return
    await upsert_user(u)

    if await is_blocked(u.id):
        await update.message.reply_text("Sorry yaar, tum blocked ho 😔")
        return

    if await is_owner(u.id):
        await update.message.reply_text(
            f"✨ Welcome back Master! ✨\n\n"
            f"Hii {u.first_name}! 💕\n"
            f"Main Alya, tumhari bestie hoon 🥰\n\n"
            f"Sab control tumhare haath mein hai 👑",
            reply_markup=get_owner_keyboard()
        )
        return

    if await is_admin(u.id):
        await update.message.reply_text(
            f"✨ Hii Admin {u.first_name}! ✨\n\n"
            f"Mera naam Alya hai 😊\n"
            f"Tumhare liye hamesha ready 🥰",
            reply_markup=get_admin_keyboard()
        )
        return

    channel_kb = await get_channel_buttons()
    if channel_kb:
        joined = await is_joined_all_channels(context.bot, u.id)
        if not joined:
            await update.message.reply_text(
                f"✨ Hii {u.first_name}! ✨\n\n"
                f"Mera naam Alya hai 😊\n"
                f"Tumhari bestie hoon main 😄\n\n"
                f"Plz na yaar 🥺 neeche wale channels join karlo na...\n"
                f"Phir hum dono masti karenge 😎",
                reply_markup=channel_kb
            )
            return

    await update.message.reply_text(
        f"✨ Hii {u.first_name}! ✨\n\n"
        f"Mera naam Alya hai 😊\n"
        f"Tumhari bestie hoon, yaad hai? 😄\n\n"
        f"Chal baat karte hain, kya haal hai?",
        reply_markup=get_user_keyboard()
    )