import asyncpg
from config import DATABASE_URL, utc_now, now_iso, logger
from datetime import datetime, timedelta, date, timezone

db_pool = None

async def init_db_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=20)
    logger.info("Database pool created")

async def get_db():
    if db_pool is None:
        raise RuntimeError("Database pool not initialized")
    return db_pool

async def init_db():
    pool = await get_db()
    async with pool.acquire() as conn:
        # Create users table with all columns
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                nickname TEXT,
                started_at TEXT,
                mood TEXT DEFAULT 'neutral'
            )
        """)
        cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
        col_names = [c['column_name'] for c in cols]

        if 'nickname' not in col_names:
            await conn.execute("ALTER TABLE users ADD COLUMN nickname TEXT")
        if 'relation' not in col_names:
            await conn.execute("ALTER TABLE users ADD COLUMN relation TEXT DEFAULT 'FRIEND'")
            logger.info("Added relation column with default FRIEND")
        if 'plan_type' not in col_names:
            await conn.execute("ALTER TABLE users ADD COLUMN plan_type TEXT DEFAULT 'free'")
        if 'plan_expiry' not in col_names:
            await conn.execute("ALTER TABLE users ADD COLUMN plan_expiry TIMESTAMP")
        if 'daily_msg_count' not in col_names:
            await conn.execute("ALTER TABLE users ADD COLUMN daily_msg_count INTEGER DEFAULT 0")
        if 'last_msg_date' not in col_names:
            await conn.execute("ALTER TABLE users ADD COLUMN last_msg_date DATE")
        if 'reminder_sent' not in col_names:
            await conn.execute("ALTER TABLE users ADD COLUMN reminder_sent BOOLEAN DEFAULT FALSE")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                role TEXT,
                text TEXT,
                ts TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id SERIAL PRIMARY KEY,
                type TEXT,
                file_id TEXT UNIQUE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT,
                added_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id BIGINT PRIMARY KEY,
                blocked_by BIGINT,
                blocked_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id SERIAL PRIMARY KEY,
                channel_id TEXT UNIQUE,
                channel_link TEXT,
                channel_name TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                api_key TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT,
                base_url TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                added_at TEXT,
                added_by BIGINT
            )
        """)
        key_cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='api_keys'")
        key_col_names = [c['column_name'] for c in key_cols]
        if 'last_error' not in key_col_names:
            await conn.execute("ALTER TABLE api_keys ADD COLUMN last_error TIMESTAMPTZ")
        if 'error_count' not in key_col_names:
            await conn.execute("ALTER TABLE api_keys ADD COLUMN error_count INTEGER DEFAULT 0")
        if 'disabled_until' not in key_col_names:
            await conn.execute("ALTER TABLE api_keys ADD COLUMN disabled_until TIMESTAMPTZ")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                user_id BIGINT PRIMARY KEY,
                window_start TIMESTAMPTZ NOT NULL,
                count INTEGER NOT NULL
            )
        """)

        await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_ts ON messages(user_id, id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_plan_expiry ON users(plan_expiry)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_is_active ON api_keys(is_active)")

    logger.info("Database initialized")

# ----- User functions -----
async def upsert_user(u):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users(user_id, first_name, username, started_at)
            VALUES($1, $2, $3, $4)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name=EXCLUDED.first_name,
                username=EXCLUDED.username
        """, u.id, u.first_name or "", u.username or "", now_iso())

async def get_user_nickname(user_id: int) -> str:
    pool = await get_db()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT nickname, first_name FROM users WHERE user_id=$1", user_id)
    if row:
        return row['nickname'] or row['first_name'] or "yaar"
    return "yaar"

async def set_user_nickname(user_id: int, nickname: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET nickname=$1 WHERE user_id=$2", nickname, user_id)

async def get_user_relation(user_id: int) -> str:
    pool = await get_db()
    async with pool.acquire() as conn:
        row = await conn.fetchval("SELECT relation FROM users WHERE user_id=$1", user_id)
        return row if row else "FRIEND"

async def set_user_relation(user_id: int, relation: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET relation=$1 WHERE user_id=$2", relation, user_id)

# ----- Plan functions -----
def get_daily_limit(plan_type: str) -> int:
    limits = {'free': 80, 'weekly': 300, 'monthly': 700, 'yearly': 1200}
    return limits.get(plan_type, 35)

async def get_user_plan(user_id: int) -> dict:
    pool = await get_db()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT plan_type, plan_expiry, daily_msg_count, last_msg_date, reminder_sent FROM users WHERE user_id=$1",
                user_id
            )
        if not row:
            return {'plan_type': 'free', 'plan_expiry': None, 'daily_msg_count': 0, 'last_msg_date': None, 'reminder_sent': False}
        return dict(row)
    except Exception as e:
        logger.error(f"Error getting plan for user {user_id}: {e}")
        return {'plan_type': 'free', 'plan_expiry': None, 'daily_msg_count': 0, 'last_msg_date': None, 'reminder_sent': False}

async def update_user_plan(user_id: int, plan_type: str, expiry_days: int):
    pool = await get_db()
    expiry_utc = utc_now() + timedelta(days=expiry_days)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET plan_type=$1, plan_expiry=$2, daily_msg_count=0, reminder_sent=FALSE WHERE user_id=$3",
            plan_type, expiry_utc, user_id
        )
    logger.info(f"User {user_id} upgraded to {plan_type} plan until {expiry_utc} UTC")

async def validate_user_exists(user_id: int) -> bool:
    pool = await get_db()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchval("SELECT 1 FROM users WHERE user_id=$1", user_id)
        return bool(row)
    except Exception:
        return False

async def reset_daily_if_needed(user_id: int):
    pool = await get_db()
    today_utc = utc_now().date()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT last_msg_date FROM users WHERE user_id=$1", user_id)
        if row and row['last_msg_date'] == today_utc:
            return
        await conn.execute(
            "UPDATE users SET daily_msg_count=0, last_msg_date=$1, reminder_sent=FALSE WHERE user_id=$2",
            today_utc, user_id
        )

async def increment_message_count(user_id: int):
    pool = await get_db()
    today = date.today()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET daily_msg_count = daily_msg_count + 1, last_msg_date=$1 WHERE user_id=$2",
            today, user_id
        )

async def check_and_downgrade_expired(user_id: int) -> bool:
    pool = await get_db()
    now_utc = utc_now()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT plan_type, plan_expiry FROM users WHERE user_id=$1", user_id)
        if row and row['plan_type'] != 'free' and row['plan_expiry'] and row['plan_expiry'] < now_utc:
            await conn.execute(
                "UPDATE users SET plan_type='free', plan_expiry=NULL, reminder_sent=FALSE WHERE user_id=$1",
                user_id
            )
            return True
    return False

async def send_expiry_reminder_if_needed(user_id: int, context):
    pool = await get_db()
    now_utc = utc_now()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT plan_type, plan_expiry, reminder_sent FROM users WHERE user_id=$1",
            user_id
        )
        if not row or row['plan_type'] == 'free' or not row['plan_expiry'] or row['reminder_sent']:
            return
        expiry = row['plan_expiry']
        if expiry - now_utc <= timedelta(days=1):
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Yaar 🥺 tumhara plan kal khatam hone wala hai.\n\n"
                         "Agar chaho to renew kar sakte ho taaki aur baat kar sake.\n\n"
                         "Check plans → /plans"
                )
                await conn.execute("UPDATE users SET reminder_sent=TRUE WHERE user_id=$1", user_id)
            except Exception as e:
                logger.warning(f"Failed to send expiry reminder to {user_id}: {e}")

async def can_send_message(user_id: int, is_owner_func, is_admin_func):
    if await is_owner_func(user_id) or await is_admin_func(user_id):
        return True, 0, ""
    await reset_daily_if_needed(user_id)
    await check_and_downgrade_expired(user_id)
    plan = await get_user_plan(user_id)
    limit = get_daily_limit(plan['plan_type'])
    if plan['daily_msg_count'] >= limit:
        return False, limit, "Yaar 🥺 daily chat limit khatam ho gayi.\n\nAgar aur baat karni hai to ek plan le lo.\n\nCheck plans → /plans"
    return True, limit, ""

# ----- Message functions -----
async def log_msg(user_id: int, role: str, text: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO messages(user_id, role, text, ts) VALUES($1, $2, $3, $4)",
            user_id, role, text[:4000], now_iso()
        )

async def get_history(user_id: int, limit: int = 10):
    pool = await get_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, text FROM messages WHERE user_id=$1 ORDER BY id DESC LIMIT $2",
            user_id, limit
        )
    return [{"role": r['role'], "content": r['text']} for r in reversed(rows)]

async def clear_user_data(user_id: int):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM messages WHERE user_id=$1", user_id)

async def clear_all_messages():
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM messages")
    logger.info("All messages cleared")

async def wipe_all_except_users():
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM messages")
        await conn.execute("DELETE FROM assets")
        await conn.execute("DELETE FROM admins")
        await conn.execute("DELETE FROM blocked_users")
        await conn.execute("DELETE FROM channels")
        await conn.execute("DELETE FROM api_keys")
    logger.info("Wiped all data except users")

# ----- Asset functions -----
async def add_asset(asset_type: str, file_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO assets (type, file_id) VALUES ($1, $2) ON CONFLICT (file_id) DO NOTHING",
            asset_type, file_id
        )

async def get_random_asset(asset_type: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT file_id FROM assets WHERE type=$1 ORDER BY RANDOM() LIMIT 1",
            asset_type
        )
    return row['file_id'] if row else None

async def get_all_assets(asset_type: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT file_id FROM assets WHERE type=$1", asset_type)
    return [r['file_id'] for r in rows]

# ----- Admin functions -----
async def add_admin(user_id: int, added_by: int):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO admins(user_id, added_by, added_at) VALUES($1, $2, $3) ON CONFLICT DO NOTHING",
            user_id, added_by, now_iso()
        )

async def remove_admin(user_id: int):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM admins WHERE user_id=$1", user_id)

async def get_all_admins():
    pool = await get_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM admins")
    return [r['user_id'] for r in rows]

# ----- Block functions -----
async def block_user(user_id: int, blocked_by: int):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO blocked_users(user_id, blocked_by, blocked_at) VALUES($1, $2, $3) ON CONFLICT DO NOTHING",
            user_id, blocked_by, now_iso()
        )

async def unblock_user(user_id: int):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM blocked_users WHERE user_id=$1", user_id)

# ----- Channel functions -----
async def add_channel(channel_id: str, channel_link: str, channel_name: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO channels(channel_id, channel_link, channel_name) VALUES($1, $2, $3) ON CONFLICT(channel_id) DO UPDATE SET channel_link=$2, channel_name=$3",
            channel_id, channel_link, channel_name
        )

async def remove_channel(channel_id: str):
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM channels WHERE channel_id=$1", channel_id)

async def get_all_channels():
    pool = await get_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT channel_id, channel_link, channel_name FROM channels")
    return [{"id": r['channel_id'], "link": r['channel_link'], "name": r['channel_name']} for r in rows]

async def is_joined_all_channels(bot, user_id: int) -> bool:
    channels = await get_all_channels()
    if not channels:
        return True
    from telegram.constants import ChatMemberStatus
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch['id'], user_id=user_id)
            if member.status not in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                return False
        except Exception:
            return False
    return True

# ----- Rate limiting -----
async def check_rate_limit(user_id: int) -> bool:
    from config import RATE_LIMIT, RATE_LIMIT_WINDOW
    pool = await get_db()
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT window_start, count FROM rate_limits WHERE user_id=$1", user_id)
        if not row:
            await conn.execute(
                "INSERT INTO rate_limits (user_id, window_start, count) VALUES ($1, $2, 1)",
                user_id, now
            )
            return True
        window_start, count = row['window_start'], row['count']
        if now - window_start > timedelta(seconds=RATE_LIMIT_WINDOW):
            await conn.execute(
                "UPDATE rate_limits SET window_start=$1, count=1 WHERE user_id=$2",
                now, user_id
            )
            return True
        if count < RATE_LIMIT:
            await conn.execute(
                "UPDATE rate_limits SET count = count + 1 WHERE user_id=$1",
                user_id
            )
            return True
        return False