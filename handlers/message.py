import re
import asyncio
import random
import telegram.error
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from config import (
    logger, get_routine_context, ALYA_SYSTEM_PROMPT,  # Note: ALYA_SYSTEM_PROMPT should be defined in config or a separate file. For brevity, we'll assume it's in config.
)
from database import (
    upsert_user, get_user_nickname, get_history, log_msg, get_random_asset,
    increment_message_count, send_expiry_reminder_if_needed, can_send_message,
    is_joined_all_channels, get_all_channels, get_db, add_asset, block_user,
    unblock_user, add_admin, remove_admin, add_channel, remove_channel
)
from utils import (
    is_blocked, is_suspicious_question, has_personal_info_request,
    SUSPICIOUS_REPLIES, PERSONAL_INFO_REPLIES, filter_ai_response,
    is_admin, is_owner, get_user_relation, OWNER_ID
)
from ai import call_ai_with_fallback
from keyboards import (
    get_confirmation_keyboard, get_channel_buttons, get_user_keyboard,
    get_admin_keyboard
)
from state import COLLECTING_MODE
from handlers.admin import (
    stats_button, broadcast_button, add_pics_button, add_stickers_button,
    view_pics_button, view_stickers_button, block_user_button, unblock_user_button
)
from handlers.owner import (
    handle_add_admin_button, handle_remove_admin_button, handle_add_channel_button,
    handle_remove_channel_button, handle_clear_msgs_button, handle_wipe_all_button
)

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        u = update.effective_user
        msg = update.message
        chat_type = update.effective_chat.type

        if not msg or not u:
            return
        await upsert_user(u)

        if await is_blocked(u.id):
            return

        from database import check_rate_limit
        if not await check_rate_limit(u.id):
            await msg.reply_text("Yaar thoda slow 😅 wait a moment.")
            return

        user_text = msg.text.strip() if msg.text else ""

        # Security checks
        if is_suspicious_question(user_text):
            await msg.reply_text(random.choice(SUSPICIOUS_REPLIES))
            logger.warning(f"Suspicious question from user {u.id}: {user_text[:100]}")
            return

        if has_personal_info_request(user_text):
            await msg.reply_text(random.choice(PERSONAL_INFO_REPLIES))
            logger.warning(f"Personal info request from user {u.id}: {user_text[:100]}")
            return

        # Clear my data button
        if user_text == "🗑️ Clear My Data":
            await msg.reply_text(
                "Yaar sach mein saari baatein bhool jaun? 🥺\nConfirm karo please...",
                reply_markup=get_confirmation_keyboard("clear_my_data")
            )
            return

        # Buy plan button
        if user_text == "Buy Plan 💎":
            from handlers.plans import plans_command
            await plans_command(update, context)
            return

        # Admin buttons
        if await is_admin(u.id) and chat_type == "private":
            if user_text == "📊 Stats":
                await stats_button(update, context)
                return
            if user_text == "📢 Broadcast":
                await broadcast_button(update, context)
                return
            if user_text == "🖼️ Add Pics":
                await add_pics_button(update, context)
                return
            if user_text == "🎭 Add Stickers":
                await add_stickers_button(update, context)
                return
            if user_text == "📸 View Pics":
                await view_pics_button(update, context)
                return
            if user_text == "🎪 View Stickers":
                await view_stickers_button(update, context)
                return
            if user_text == "🚫 Block User":
                await block_user_button(update, context)
                return
            if user_text == "✅ Unblock User":
                await unblock_user_button(update, context)
                return

        # Owner buttons
        if await is_owner(u.id) and chat_type == "private":
            if user_text == "➕ Add Admin":
                await handle_add_admin_button(update, context)
                return
            if user_text == "➖ Remove Admin":
                await handle_remove_admin_button(update, context)
                return
            if user_text == "📺 Add Channel":
                await handle_add_channel_button(update, context)
                return
            if user_text == "❌ Remove Channel":
                await handle_remove_channel_button(update, context)
                return
            if user_text == "🗑️ Clear Msgs":
                await handle_clear_msgs_button(update, context)
                return
            if user_text == "🧹 Wipe All":
                await handle_wipe_all_button(update, context)
                return

        # Collecting mode handlers
        if u.id in COLLECTING_MODE:
            mode = COLLECTING_MODE[u.id]
            if user_text.lower() == "cancel":
                COLLECTING_MODE.pop(u.id, None)
                await msg.reply_text("❌ Cancelled!")
                return

            if mode == "broadcast":
                content = {}
                if msg.photo:
                    content['type'] = 'photo'
                    content['file_id'] = msg.photo[-1].file_id
                    content['caption'] = msg.caption or ""
                elif msg.sticker:
                    content['type'] = 'sticker'
                    content['file_id'] = msg.sticker.file_id
                    content['caption'] = None
                else:
                    content['type'] = 'text'
                    content['text'] = msg.text
                context.user_data['broadcast_content'] = content
                COLLECTING_MODE.pop(u.id, None)
                pool = await get_db()
                async with pool.acquire() as conn:
                    users = await conn.fetch("SELECT user_id FROM users")
                success = failed = 0
                await msg.reply_text(f"📢 Broadcasting to {len(users)} users...")

                sem = asyncio.Semaphore(5)

                async def safe_send(uid):
                    nonlocal success, failed
                    async with sem:
                        try:
                            if content['type'] == 'photo':
                                await context.bot.send_photo(chat_id=uid, photo=content['file_id'], caption=content['caption'])
                            elif content['type'] == 'sticker':
                                await context.bot.send_sticker(chat_id=uid, sticker=content['file_id'])
                            else:
                                await context.bot.send_message(chat_id=uid, text=content['text'])
                            success += 1
                        except telegram.error.RetryAfter as e:
                            logger.warning(f"Flood wait for {uid}, sleeping {e.retry_after}s")
                            await asyncio.sleep(e.retry_after)
                            try:
                                if content['type'] == 'photo':
                                    await context.bot.send_photo(chat_id=uid, photo=content['file_id'], caption=content['caption'])
                                elif content['type'] == 'sticker':
                                    await context.bot.send_sticker(chat_id=uid, sticker=content['file_id'])
                                else:
                                    await context.bot.send_message(chat_id=uid, text=content['text'])
                                success += 1
                            except Exception:
                                failed += 1
                        except Exception:
                            failed += 1

                tasks = [safe_send(row['user_id']) for row in users]
                await asyncio.gather(*tasks, return_exceptions=True)
                await msg.reply_text(f"✅ Broadcast complete!\n• Success: {success}\n• Failed: {failed}")
                context.user_data.pop('broadcast_content', None)
                return

            if user_text.lower() == "done":
                m = COLLECTING_MODE.pop(u.id, None)
                await msg.reply_text(f"✅ {m or 'Collection'} mode ended!")
                return

            if mode == "pic":
                file_id = None
                if msg.photo:
                    file_id = msg.photo[-1].file_id
                elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
                    file_id = msg.document.file_id
                if file_id:
                    await add_asset("pic", file_id)
                    await msg.reply_text("✅ Pic added! More bhejo ya 'done' likho.")
                return

            if mode == "sticker" and msg.sticker:
                await add_asset("sticker", msg.sticker.file_id)
                await msg.reply_text("✅ Sticker added! More bhejo ya 'done' likho.")
                return

            if mode == "block":
                COLLECTING_MODE.pop(u.id, None)
                try:
                    target_id = int(user_text)
                    if target_id == OWNER_ID:
                        await msg.reply_text("Owner ko block nahi kar sakte 😅")
                        return
                    await block_user(target_id, u.id)
                    await msg.reply_text(f"✅ User `{target_id}` blocked!", parse_mode="Markdown")
                except ValueError:
                    await msg.reply_text("Invalid user ID!")
                return

            if mode == "unblock":
                COLLECTING_MODE.pop(u.id, None)
                try:
                    target_id = int(user_text)
                    await unblock_user(target_id)
                    await msg.reply_text(f"✅ User `{target_id}` unblocked!", parse_mode="Markdown")
                except ValueError:
                    await msg.reply_text("Invalid user ID!")
                return

            if mode == "add_admin":
                COLLECTING_MODE.pop(u.id, None)
                try:
                    target_id = int(user_text)
                    await add_admin(target_id, u.id)
                    await msg.reply_text(f"✅ User `{target_id}` is now admin!", parse_mode="Markdown")
                    try:
                        await context.bot.send_message(
                            chat_id=target_id,
                            text="🎉 Congratulations! 🎉\n\nTumhe Admin promote kar diya gaya hai! 💫\nAb tum bot manage kar sakte ho.\n\n/start dabao apna admin panel dekhne ke liye 👑",
                            reply_markup=get_admin_keyboard()
                        )
                    except Exception:
                        pass
                except ValueError:
                    await msg.reply_text("Invalid user ID!")
                return

            if mode == "remove_admin":
                COLLECTING_MODE.pop(u.id, None)
                try:
                    target_id = int(user_text)
                    await remove_admin(target_id)
                    await msg.reply_text(f"✅ User `{target_id}` removed from admins!", parse_mode="Markdown")
                except ValueError:
                    await msg.reply_text("Invalid user ID!")
                return

            if mode == "add_channel_link":
                COLLECTING_MODE[u.id] = ("add_channel_id", user_text)
                await msg.reply_text("Ab channel ID bhejo (e.g., -1001234567890 ya @channelname):")
                return

            if isinstance(mode, tuple) and mode[0] == "add_channel_id":
                channel_link = mode[1]
                channel_id = user_text
                COLLECTING_MODE[u.id] = ("add_channel_name", channel_link, channel_id)
                await msg.reply_text("Channel ka display name bhejo (e.g., My Channel):")
                return

            if isinstance(mode, tuple) and mode[0] == "add_channel_name":
                channel_link = mode[1]
                channel_id = mode[2]
                channel_name = user_text
                COLLECTING_MODE.pop(u.id, None)
                await add_channel(channel_id, channel_link, channel_name)
                await msg.reply_text(f"✅ Channel added!\n• Name: {channel_name}\n• ID: `{channel_id}`", parse_mode="Markdown")
                return

            if mode == "remove_channel":
                COLLECTING_MODE.pop(u.id, None)
                await remove_channel(user_text)
                await msg.reply_text(f"✅ Channel `{user_text}` removed!", parse_mode="Markdown")
                return

        # Group chat logic
        if chat_type in ("group", "supergroup"):
            me = await context.bot.get_me()
            bot_username = me.username or ""
            mentioned = bool(re.search(r"\balya\b", user_text, flags=re.IGNORECASE)) or \
                        (bot_username and re.search(rf"@{re.escape(bot_username)}\b", user_text, flags=re.IGNORECASE))
            is_reply_to_bot = msg.reply_to_message and msg.reply_to_message.from_user and msg.reply_to_message.from_user.id == me.id
            if not (mentioned or is_reply_to_bot):
                return

        # Private chat channel check
        if chat_type == "private" and not await is_owner(u.id) and not await is_admin(u.id):
            channels = await get_all_channels()
            if channels and not await is_joined_all_channels(context.bot, u.id):
                channel_kb = await get_channel_buttons()
                await msg.reply_text(
                    "Yaar pehle channels join karo na 🥺\nPlz plz plz... meri baat maan lo 😊",
                    reply_markup=channel_kb
                )
                return

        # Plan limit check
        allowed, limit, limit_msg = await can_send_message(u.id, is_owner, is_admin)
        if not allowed:
            await msg.reply_text(limit_msg)
            return

        # Alya AI chat
        is_sticker = bool(msg.sticker)
        if is_sticker:
            user_text = f"[User sent a sticker: {msg.sticker.emoji or 'unknown'}]"

        if not user_text and not is_sticker:
            return

        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)

        if chat_type == "private":
            await log_msg(u.id, "user", user_text)

        pic_triggers = ["pic", "photo", "selfie", "dekhna", "dikha", "show me", "send pic", "apni pic", "tumhari pic", "face", "cute pic"]
        trigger_detected = any(t in user_text.lower() for t in pic_triggers)

        nickname = await get_user_nickname(u.id)
        history = await get_history(u.id, limit=10)

        messages = [{"role": "system", "content": ALYA_SYSTEM_PROMPT}]
        messages.append({"role": "system", "content": f"Current real‑time info: {get_routine_context()}"})

        context_info = f"User's name/nickname: {nickname}. "
        if chat_type != "private":
            context_info += "This is a GROUP chat. Keep replies short. "
        else:
            context_info += "This is PRIVATE DM. Be friendly and casual. "

        if is_sticker:
            context_info += "User sent a sticker. You may respond with [SEND_STICKER] tag. "
        if trigger_detected:
            context_info += "User is asking for your photo. Include [SEND_PHOTO] in response. "

        messages.append({"role": "system", "content": context_info})

        relation = await get_user_relation(u.id)
        messages.append({
            "role": "system",
            "content": f"Your relationship with the user is: {relation}. "
                       f"Act accordingly: if FRIEND be friendly, supportive, and platonic; if GF be loving/possessive; if ASSISTANT be professional."
        })

        messages.extend(history)
        if not history or history[-1].get("content") != user_text:
            messages.append({"role": "user", "content": user_text})

        reply = await call_ai_with_fallback(messages, nickname)
        if reply:
            reply = filter_ai_response(reply)
            if not reply:
                reply = "Hmm, kuch to problem hai 😅"
        else:
            reply = "Hmm me abhi busy hu thodi der bad baat karte hain?"

        send_photo = bool(re.search(r'\[SEND_PHOTO\]', reply, re.IGNORECASE)) or trigger_detected
        send_sticker = bool(re.search(r'\[SEND_STICKER\]', reply, re.IGNORECASE)) and is_sticker

        clean_reply = re.sub(r'\[SEND_PHOTO\]', '', reply, flags=re.IGNORECASE)
        clean_reply = re.sub(r'\[SEND_STICKER\]', '', clean_reply, flags=re.IGNORECASE).strip()

        if chat_type == "private":
            await log_msg(u.id, "assistant", clean_reply)

        if clean_reply:
            await msg.reply_text(clean_reply)

        if send_photo:
            pid = await get_random_asset("pic")
            if pid:
                try:
                    await context.bot.send_photo(chat_id=msg.chat_id, photo=pid)
                except Exception as e:
                    logger.warning(f"Failed to send photo: {e}")

        if send_sticker:
            sid = await get_random_asset("sticker")
            if sid:
                try:
                    await context.bot.send_sticker(chat_id=msg.chat_id, sticker=sid)
                except Exception as e:
                    logger.warning(f"Failed to send sticker: {e}")

        await increment_message_count(u.id)
        await send_expiry_reminder_if_needed(u.id, context)

    except Exception as e:
        logger.error(f"Unhandled exception in chat handler for user {update.effective_user.id}: {e}", exc_info=True)
        try:
            await update.message.reply_text("Yaar, kuch technical error aa gaya. Thodi der mein try karo 😅")
        except:
            pass