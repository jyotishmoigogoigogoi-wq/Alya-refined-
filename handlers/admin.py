from telegram import Update
from telegram.ext import ContextTypes
from database import (
    get_db, get_all_assets, add_asset, block_user, unblock_user, get_all_channels
)
from utils import is_admin, is_owner, OWNER_ID
from config import logger
from state import COLLECTING_MODE
from keyboards import get_confirmation_keyboard

async def stats_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    pool = await get_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, first_name, username, started_at FROM users ORDER BY started_at DESC")
    lines = [f"📊 Total Users: {len(rows)}\n"]
    for i, row in enumerate(rows[:50]):
        uname = f"@{row['username']}" if row['username'] else "-"
        lines.append(f"{i+1}. {row['first_name']} ({uname}) | `{row['user_id']}`")
    if len(rows) > 50:
        lines.append(f"\n...and {len(rows)-50} more")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def broadcast_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    COLLECTING_MODE[update.effective_user.id] = "broadcast"
    await update.message.reply_text("📢 Broadcast message bhejo (text, photo ya sticker).\nCancel karne ke liye 'cancel' likho.")

async def add_pics_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    COLLECTING_MODE[update.effective_user.id] = "pic"
    await update.message.reply_text("🖼️ Photos bhejo jo add karni hain.\n'done' likho band karne ke liye.")

async def add_stickers_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    COLLECTING_MODE[update.effective_user.id] = "sticker"
    await update.message.reply_text("🎭 Stickers bhejo jo add karne hain.\n'done' likho band karne ke liye.")

async def view_pics_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pics = await get_all_assets("pic")
    if not pics:
        await update.message.reply_text("Koi pics saved nahi hain 😢")
        return
    await update.message.reply_text(f"📸 Total {len(pics)} pics hain. Bhej rahi hoon...")
    for pid in pics[:20]:
        try:
            await context.bot.send_photo(chat_id=update.message.chat_id, photo=pid)
        except Exception:
            continue

async def view_stickers_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stickers = await get_all_assets("sticker")
    if not stickers:
        await update.message.reply_text("Koi stickers saved nahi hain 😢")
        return
    await update.message.reply_text(f"🎪 Total {len(stickers)} stickers hain. Bhej rahi hoon...")
    for sid in stickers[:20]:
        try:
            await context.bot.send_sticker(chat_id=update.message.chat_id, sticker=sid)
        except Exception:
            continue

async def block_user_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    COLLECTING_MODE[update.effective_user.id] = "block"
    await update.message.reply_text("🚫 User ID bhejo jisko block karna hai:")

async def unblock_user_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    COLLECTING_MODE[update.effective_user.id] = "unblock"
    await update.message.reply_text("✅ User ID bhejo jisko unblock karna hai:")