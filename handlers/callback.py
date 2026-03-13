from telegram import Update
from telegram.ext import ContextTypes
from database import (
    is_joined_all_channels, clear_user_data, clear_all_messages,
    wipe_all_except_users
)
from utils import is_admin  # <--- YAHAN SE IMPORT KARO, database se nahi
from keyboards import get_user_keyboard, get_contact_owner_keyboard
from config import logger

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u = update.effective_user
    await q.answer()
    data = q.data

    if data == "check_join":
        joined = await is_joined_all_channels(context.bot, u.id)
        if joined:
            await q.edit_message_text(
                "✅ Approved! \n\nThank you yaar! 😊 Ab baat karte hain."
            )
            await context.bot.send_message(
                chat_id=u.id,
                text="Ab batao, kya haal hai?",
                reply_markup=get_user_keyboard()
            )
        else:
            await q.answer("Yaar abhi tak join nahi kiya 🥺 Plz join karo na!", show_alert=True)
        return

    if data == "confirm_clear_my_data":
        await clear_user_data(u.id)
        await q.edit_message_text("Done yaar! Tumhari saari baatein bhool gayi main 😢")
        return

    if data == "confirm_clear_msgs":
        if not await is_admin(u.id):
            await q.answer("Access denied!", show_alert=True)
            return
        await clear_all_messages()
        await q.edit_message_text("✅ All messages cleared! Users, pics, stickers safe hain.")
        return

    if data == "confirm_wipe_all":
        if not await is_admin(u.id):
            await q.answer("Access denied!", show_alert=True)
            return
        await wipe_all_except_users()
        await q.edit_message_text("✅ Wipe complete! Sirf users ki list bachi hai.")
        return

    if data == "cancel_action":
        await q.edit_message_text("❌ Action cancelled!")
        return

    if data == "plan_buy":
        await q.edit_message_text(
            "💎 Premium Plans 💎\n\nWeekly – ₹??\nMonthly – ₹??\nYearly – ₹??\n\nContact owner to purchase.",
            reply_markup=get_contact_owner_keyboard()
        )
        return
    if data == "plan_cancel":
        await q.delete_message()
        return
