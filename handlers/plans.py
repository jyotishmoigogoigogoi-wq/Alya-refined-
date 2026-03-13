from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timedelta, timezone
from database import (
    get_user_plan, get_daily_limit, update_user_plan, validate_user_exists,
    utc_now, get_db
)
from utils import is_owner, is_blocked
from keyboards import get_plans_keyboard, get_contact_owner_keyboard
from config import logger

async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if await is_blocked(u.id):
        await update.message.reply_text("Sorry yaar, tum blocked ho 😔")
        return
    text = (
        "✨ Alya Premium Plans ✨\n\n"
        "Free → 80 msgs/day\n"
        "Weekly → 300 msgs/day\n"
        "Monthly → 700 msgs/day\n"
        "Yearly → 1200 msgs/day\n\n"
        "Want more time? 🥺"
    )
    await update.message.reply_text(text, reply_markup=get_plans_keyboard())

async def giveplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not await is_owner(u.id):
        await update.message.reply_text("This command is only for my master 👑")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "❌ Usage: /giveplan <user_id> <plan>\n\n"
            "Examples:\n/giveplan 123456789 weekly\n/giveplan 123456789 monthly\n/giveplan 123456789 yearly"
        )
        return

    try:
        target_id = int(args[0])
        plan = args[1].lower()
        valid_plans = ('weekly', 'monthly', 'yearly')
        if plan not in valid_plans:
            await update.message.reply_text(f"❌ Invalid plan. Must be one of: {', '.join(valid_plans)}")
            return

        user_exists = await validate_user_exists(target_id)
        if not user_exists:
            await update.message.reply_text(
                f"⚠️ Warning: User {target_id} hasn't started the bot yet.\n"
                f"Plan will be saved but they won't get notification until they /start."
            )

        expiry_days = {'weekly': 7, 'monthly': 30, 'yearly': 365}[plan]
        await update_user_plan(target_id, plan, expiry_days)

        await update.message.reply_text(
            f"✅ Plan granted successfully!\n\n"
            f"• User: `{target_id}`\n"
            f"• Plan: {plan.capitalize()}\n"
            f"• Duration: {expiry_days} days\n"
            f"• Daily limit: {get_daily_limit(plan)} messages",
            parse_mode="Markdown"
        )

        if user_exists:
            try:
                expiry_utc = utc_now() + timedelta(days=expiry_days)
                expiry_ist = expiry_utc.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"🎉 **Congratulations Yaar!** 🎉\n\n"
                         f"Your **{plan.capitalize()} Premium Plan** is now active! 😊\n\n"
                         f"📊 **Plan Details:**\n"
                         f"• Daily Messages: {get_daily_limit(plan)}\n"
                         f"• Valid for: {expiry_days} days\n"
                         f"• Expires: {expiry_ist.strftime('%d %B %Y')}\n\n"
                         f"Now we can chat even more! 🥰\n"
                         f"Type /plans to check your plan status.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {target_id}: {e}")
                await update.message.reply_text(
                    f"⚠️ Plan granted but couldn't notify user (they might have blocked the bot)."
                )
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
    except Exception as e:
        logger.error(f"Error in giveplan_command: {e}")
        await update.message.reply_text(f"❌ An error occurred: {str(e)}")

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    chat = update.effective_chat
    await context.bot.send_chat_action(chat_id=chat.id, action="typing")

    plan = await get_user_plan(u.id)
    plan_type = plan['plan_type'].upper()
    expiry_utc = plan['plan_expiry']

    if expiry_utc:
        expiry_aware = expiry_utc.replace(tzinfo=timezone.utc)
        expiry_ist = expiry_aware.astimezone(timezone(timedelta(hours=5, minutes=30)))
        now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        remaining = expiry_ist - now_ist
        days_left = remaining.days
        hours_left = remaining.seconds // 3600
        if remaining.total_seconds() <= 0:
            expiry_text = "⚠️ Already expired!"
        elif days_left > 0:
            expiry_text = f"⏳ {days_left} days, {hours_left} hrs left"
        elif hours_left > 0:
            expiry_text = f"⏳ {hours_left} hours left"
        else:
            expiry_text = "⚠️ Expires today!"
        expiry_date = expiry_ist.strftime("%d %b %Y, %I:%M %p")
        expiry_status = f"📅 {expiry_date}\n{expiry_text}"
    else:
        expiry_status = "♾️ Lifetime (Free Plan)"

    today_msgs = plan['daily_msg_count']
    daily_limit = get_daily_limit(plan['plan_type'])

    pool = await get_db()
    async with pool.acquire() as conn:
        total_msgs = await conn.fetchval("SELECT COUNT(*) FROM messages WHERE user_id=$1", u.id) or 0

    plan_emoji = {'free': '🆓', 'weekly': '⚡', 'monthly': '💎', 'yearly': '👑'}.get(plan['plan_type'], '📱')

    text = f"""
╔════════════════════╗
║   💎 YOUR PROFILE  ║
╚════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━
📊 **PLAN DETAILS**
━━━━━━━━━━━━━━━━━━━━━━━━
• **Current Plan:** {plan_emoji} **{plan_type}**
• **Messages Today:** {today_msgs}/{daily_limit}
• **Total Messages:** {total_msgs}

━━━━━━━━━━━━━━━━━━━━━━━━
⏰ **EXPIRY INFO**
━━━━━━━━━━━━━━━━━━━━━━━━
{expiry_status}

━━━━━━━━━━━━━━━━━━━━━━━━
✨ Use /plans to upgrade
    """
    if daily_limit > 0:
        percent = (today_msgs / daily_limit) * 100
        filled = int(percent / 10)
        bar = "█" * filled + "░" * (10 - filled)
        text += f"\n📊 **Usage:** {bar} {percent:.1f}%"

    await update.message.reply_text(text, parse_mode="Markdown")