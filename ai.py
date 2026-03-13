import asyncio
from datetime import datetime, timedelta, timezone
from openai import AsyncOpenAI
from config import AI_CONCURRENCY_LIMIT, AI_REQUEST_TIMEOUT, AI_MAX_TOKENS, AI_TEMPERATURE, logger
from database import get_db

ai_semaphore = asyncio.Semaphore(AI_CONCURRENCY_LIMIT)

async def call_ai_with_fallback(messages, nickname):
    pool = await get_db()
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, api_key, model, base_url, error_count, disabled_until
            FROM api_keys
            WHERE is_active = TRUE
              AND (disabled_until IS NULL OR disabled_until < $1)
            ORDER BY error_count ASC, last_error ASC NULLS FIRST
        """, now)
    if not rows:
        return "Yaar 🥺 koi API key nahi hai, owner se baat karo..."

    for row in rows:
        key_id = row['id']
        api_key = row['api_key']
        model = row['model']
        base_url = row['base_url']
        try:
            async with ai_semaphore:
                client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=AI_MAX_TOKENS,
                        temperature=AI_TEMPERATURE,
                    ),
                    timeout=AI_REQUEST_TIMEOUT
                )
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE api_keys SET error_count = 0, disabled_until = NULL, last_error = NULL WHERE id = $1",
                    key_id
                )
            logger.info(f"✅ Key ID {key_id} used for {nickname}")
            return response.choices[0].message.content
        except asyncio.TimeoutError:
            logger.warning(f"Key ID {key_id} timeout")
            await _record_key_failure(key_id)
        except Exception as e:
            logger.warning(f"Key ID {key_id} failed: {type(e).__name__}: {e}")
            await _record_key_failure(key_id)
    return "Sab keys fail ho gayi yaar, thodi der mein try karo 😅"

async def _record_key_failure(key_id: int):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE api_keys
            SET error_count = error_count + 1,
                last_error = $1
            WHERE id = $2
        """, datetime.now(timezone.utc), key_id)
        await conn.execute("""
            UPDATE api_keys
            SET disabled_until = $1
            WHERE id = $2 AND error_count >= 3
        """, datetime.now(timezone.utc) + timedelta(minutes=5), key_id)