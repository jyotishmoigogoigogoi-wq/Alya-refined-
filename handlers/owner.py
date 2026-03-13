from telegram import Update
from telegram.ext import ContextTypes
from database import (
    add_admin, remove_admin, get_all_admins, add_channel, remove_channel,
    get_all_channels, get_db
)
from utils import is_owner, detect_provider
from config import now_iso, logger
from state import COLLECTING_MODE
from keyboards import get_admin_keyboard, get_confirmation_keyboard

async def addapi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not await is_owner(u.id):
        await update.message.reply_text("This command is only for my master 👑")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /addapi <api_key> <model>")
        return
    api_key = args[0]
    model = args[1]
    provider, base_url = detect_provider(api_key)
    if provider == "unknown" or not base_url:
        await update.message.reply_text("❌ Unknown provider or unsupported API key format.")
        return
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO api_keys (api_key, model, provider, base_url, added_at, added_by, error_count) VALUES ($1, $2, $3, $4, $5, $6, 0)",
            api_key, model, provider, base_url, now_iso(), u.id
        )
    await update.message.reply_text(f"✅ API key added successfully!\nProvider: {provider}\nModel: {model}")

async def listapi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not await is_owner(u.id):
        await update.message.reply_text("This command is only for my master 👑")
        return
    try:
        pool = await get_db()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, api_key, model, provider, is_active, error_count, disabled_until FROM api_keys ORDER BY id")
        if not rows:
            await update.message.reply_text("📭 No API keys found in database.")
            return
        message = "🔮 **KEY VAULT** 🔮\n\n"
        from datetime import datetime, timezone, timedelta
        for r in rows:
            masked = r['api_key'][:6] + "•••" + r['api_key'][-4:] if len(r['api_key']) > 15 else "••••••••"
            status_emoji = "⚡️" if r['is_active'] else "💤"
            status_text = "ACTIVE" if r['is_active'] else "DISABLED"
            disabled = f" (disabled until {r['disabled_until'].astimezone(timezone(timedelta(hours=5, minutes=30))).strftime('%H:%M')})" if r['disabled_until'] and r['disabled_until'] > datetime.now(timezone.utc) else ""
            message += f"[ID: {r['id']}] {status_emoji} **{status_text}**{disabled}\n"
            message += f"├─ Provider: **{r['provider'].title()}**\n"
            message += f"├─ Model: `{r['model']}`\n"
            message += f"├─ Errors: {r['error_count']}\n"
            message += f"└─ Key: `{masked}`\n\n"
        await update.message.reply_text(message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in listapi_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def removeapi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not await is_owner(u.id):
        await update.message.reply_text("This command is only for my master 👑")
        return
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Usage: /removeapi <id>")
        return
    try:
        key_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Invalid ID. Must be a number.")
        return
    pool = await get_db()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM api_keys WHERE id = $1", key_id)
        if result == "DELETE 0":
            await update.message.reply_text(f"No key found with ID {key_id}.")
        else:
            await update.message.reply_text(f"✅ Key ID {key_id} removed.")

async def testapi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not await is_owner(u.id):
        await update.message.reply_text("This command is only for my master 👑")
        return
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Usage: /testapi <api_key>")
        return
    api_key = args[0]
    provider, base_url = detect_provider(api_key)
    if provider == "unknown" or not base_url:
        await update.message.reply_text("❌ Unknown provider or unsupported API key format.")
        return
    await update.message.reply_text(f"Testing {provider} key... Please wait.")
    try:
        from openai import AsyncOpenAI
        import asyncio
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        model = "gpt-3.5-turbo" if provider == "openai" else "llama3-8b-8192" if provider == "groq" else "mistralai/mistral-7b-instruct"
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Say 'hi' in one word."}],
                max_tokens=5,
                temperature=0
            ),
            timeout=10
        )
        await update.message.reply_text(f"✅ Key is working! Response: {response.choices[0].message.content}")
    except Exception as e:
        await update.message.reply_text(f"❌ Key test failed: {str(e)}")

async def shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not await is_owner(u.id):
        await update.message.reply_text("This command is only for my master 👑")
        return
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE api_keys SET is_active = FALSE")
    await update.message.reply_text("🔴 All API keys disabled. Bot will not respond to AI queries until /restart.")

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not await is_owner(u.id):
        await update.message.reply_text("This command is only for my master 👑")
        return
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE api_keys SET is_active = TRUE")
    await update.message.reply_text("🟢 All API keys enabled. Bot is back online.")

# Owner button handlers (used in message.py)
async def handle_add_admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    COLLECTING_MODE[update.effective_user.id] = "add_admin"
    await update.message.reply_text("➕ User ID bhejo jisko admin banana hai:")

async def handle_remove_admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await get_all_admins()
    if not admins:
        await update.message.reply_text("Koi admin nahi hai abhi.")
        return
    COLLECTING_MODE[update.effective_user.id] = "remove_admin"
    admin_list = "\n".join([f"• `{a}`" for a in admins])
    await update.message.reply_text(f"Current Admins:\n{admin_list}\n\nUser ID bhejo jisko remove karna hai:", parse_mode="Markdown")

async def handle_add_channel_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    COLLECTING_MODE[update.effective_user.id] = "add_channel_link"
    await update.message.reply_text("📺 Channel ka invite link bhejo (e.g., https://t.me/channel):")

async def handle_remove_channel_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = await get_all_channels()
    if not channels:
        await update.message.reply_text("Koi channel set nahi hai abhi.")
        return
    COLLECTING_MODE[update.effective_user.id] = "remove_channel"
    ch_list = "\n".join([f"• {c['name']} | `{c['id']}`" for c in channels])
    await update.message.reply_text(f"Current Channels:\n{ch_list}\n\nChannel ID bhejo jisko remove karna hai:", parse_mode="Markdown")

async def handle_clear_msgs_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ Sirf messages delete honge:\n- Saari messages (sab users ki)\n\nPics, stickers, users list safe rahenge.\nPakka karna hai?",
        reply_markup=get_confirmation_keyboard("clear_msgs")
    )

async def handle_wipe_all_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ DANGER! Sab kuch delete ho jayega:\n- All messages\n- All pics/stickers\n- All admins\n- All blocked users\n- All channels\n\nSirf users ki list bachegi.\nPakka karna hai?",
        reply_markup=get_confirmation_keyboard("wipe_all")
    )