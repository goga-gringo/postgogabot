import asyncpg
from bot.config import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def init_pool():
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    with open("schema.sql", "r", encoding="utf-8") as f:
        schema = f.read()
    async with _pool.acquire() as conn:
        await conn.execute(schema)
    return _pool


def pool() -> asyncpg.Pool:
    assert _pool is not None, "DB pool is not initialized yet"
    return _pool


# ---------- users ----------

async def get_or_create_user(tg_id: int) -> int:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (tg_id) VALUES ($1)
            ON CONFLICT (tg_id) DO UPDATE SET tg_id = EXCLUDED.tg_id
            RETURNING id
            """,
            tg_id,
        )
        return row["id"]


async def get_user(user_id: int):
    async with pool().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)


async def set_user_timezone(user_id: int, timezone: str | None):
    async with pool().acquire() as conn:
        await conn.execute("UPDATE users SET timezone = $2 WHERE id = $1", user_id, timezone)


async def set_user_default_delete_after(user_id: int, hours: int | None):
    async with pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET default_delete_after_hours = $2 WHERE id = $1", user_id, hours
        )


async def set_user_language(user_id: int, language: str):
    async with pool().acquire() as conn:
        await conn.execute("UPDATE users SET language = $2 WHERE id = $1", user_id, language)


async def set_last_message_id(user_id: int, message_id: int | None):
    async with pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_bot_message_id = $2 WHERE id = $1", user_id, message_id
        )


# ---------- channels ----------

async def add_channel(owner_id: int, chat_id: int, title: str) -> int:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO channels (owner_id, chat_id, title)
            VALUES ($1, $2, $3)
            ON CONFLICT (owner_id, chat_id) DO UPDATE SET title = EXCLUDED.title
            RETURNING id
            """,
            owner_id, chat_id, title,
        )
        return row["id"]


async def list_channels(owner_id: int):
    async with pool().acquire() as conn:
        return await conn.fetch(
            "SELECT id, chat_id, title FROM channels WHERE owner_id = $1 ORDER BY added_at",
            owner_id,
        )


async def get_channel(channel_id: int):
    async with pool().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM channels WHERE id = $1", channel_id)


async def remove_channel(owner_id: int, channel_id: int):
    async with pool().acquire() as conn:
        await conn.execute(
            "DELETE FROM channels WHERE id = $1 AND owner_id = $2", channel_id, owner_id
        )


# ---------- posts ----------

async def create_post(
    owner_id: int, text: str | None, media_type: str | None, file_id: str | None,
    entities_json: str | None = None,
    source_chat_id: int | None = None, source_message_ids: list[int] | None = None,
    button_json: str | None = None,
) -> int:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO posts (owner_id, text, media_type, file_id, entities_json,
                                source_chat_id, source_message_ids, button_json)
            VALUES ($1, $2, $3, $4, $5, $6, $7::bigint[], $8)
            RETURNING id
            """,
            owner_id, text, media_type, file_id, entities_json, source_chat_id, source_message_ids, button_json,
        )
        return row["id"]


async def get_post(post_id: int):
    async with pool().acquire() as conn:
        return await conn.fetchrow("SELECT * FROM posts WHERE id = $1", post_id)


async def update_post_text(post_id: int, text: str | None, entities_json: str | None = None):
    async with pool().acquire() as conn:
        await conn.execute(
            "UPDATE posts SET text = $2, entities_json = $3, text_edited = true WHERE id = $1",
            post_id, text, entities_json,
        )


async def list_user_posts(owner_id: int, limit: int = 15):
    """Список для 'Мои посты'. Старше 30 дней не показываем — но реально их
    к этому моменту уже нет в БД, см. purge_old_posts()."""
    async with pool().acquire() as conn:
        return await conn.fetch(
            """
            SELECT p.id, p.text, p.media_type, p.created_at,
                   COUNT(pt.id) AS targets_count,
                   COUNT(*) FILTER (WHERE pt.status = 'published') AS published_count,
                   COUNT(*) FILTER (WHERE pt.status = 'scheduled') AS scheduled_count,
                   COUNT(*) FILTER (WHERE pt.status != 'deleted') AS active_count
            FROM posts p
            JOIN post_targets pt ON pt.post_id = p.id
            WHERE p.owner_id = $1 AND p.created_at > now() - interval '30 days'
            GROUP BY p.id
            HAVING COUNT(*) FILTER (WHERE pt.status != 'deleted') > 0
            ORDER BY p.created_at DESC
            LIMIT $2
            """,
            owner_id, limit,
        )


async def purge_old_posts(days: int = 30) -> int:
    """Физически удаляет из БД посты старше N дней, у которых не осталось
    ни одной ЗАПЛАНИРОВАННОЙ (ещё не опубликованной) цели — чтобы случайно
    не стереть пост, запланированный далеко вперёд. Каскадом уходят и
    post_media, и post_targets (ON DELETE CASCADE в схеме). Возвращает
    количество удалённых постов."""
    async with pool().acquire() as conn:
        rows = await conn.fetch(
            """
            DELETE FROM posts p
            WHERE p.created_at < now() - interval '1 day' * $1
              AND NOT EXISTS (
                  SELECT 1 FROM post_targets pt
                  WHERE pt.post_id = p.id AND pt.status = 'scheduled'
              )
            RETURNING p.id
            """,
            days,
        )
        return len(rows)


# ---------- album items (post_media) ----------

async def add_album_items(post_id: int, items: list[dict]):
    async with pool().acquire() as conn:
        async with conn.transaction():
            for position, item in enumerate(items):
                await conn.execute(
                    """
                    INSERT INTO post_media (post_id, position, media_type, file_id)
                    VALUES ($1, $2, $3, $4)
                    """,
                    post_id, position, item["type"], item["file_id"],
                )


async def get_album_items(post_id: int):
    async with pool().acquire() as conn:
        return await conn.fetch(
            "SELECT media_type, file_id FROM post_media WHERE post_id = $1 ORDER BY position",
            post_id,
        )


# ---------- post_targets ----------

async def create_targets(post_id: int, channel_ids: list[int], publish_at, delete_after_hours: int | None):
    async with pool().acquire() as conn:
        async with conn.transaction():
            for ch_id in channel_ids:
                await conn.execute(
                    """
                    INSERT INTO post_targets (post_id, channel_id, publish_at, delete_after_hours)
                    VALUES ($1, $2, $3, $4)
                    """,
                    post_id, ch_id, publish_at, delete_after_hours,
                )


async def fetch_due_to_publish():
    async with pool().acquire() as conn:
        return await conn.fetch(
            """
            SELECT pt.id AS target_id, pt.post_id, pt.channel_id, pt.delete_after_hours,
                   p.text, p.media_type, p.file_id, p.entities_json, p.button_json,
                   p.source_chat_id, p.source_message_ids, p.text_edited,
                   c.chat_id
            FROM post_targets pt
            JOIN posts p ON p.id = pt.post_id
            JOIN channels c ON c.id = pt.channel_id
            WHERE pt.status = 'scheduled' AND pt.publish_at <= now()
            """
        )


async def mark_published(target_id: int, message_ids: list[int], delete_after_hours: int | None):
    async with pool().acquire() as conn:
        if delete_after_hours:
            await conn.execute(
                """
                UPDATE post_targets
                SET status = 'published', message_ids = $2::bigint[], published_at = now(),
                    delete_at = now() + ($3 * INTERVAL '1 hour')
                WHERE id = $1
                """,
                target_id, message_ids, delete_after_hours,
            )
        else:
            await conn.execute(
                """
                UPDATE post_targets
                SET status = 'published', message_ids = $2::bigint[], published_at = now()
                WHERE id = $1
                """,
                target_id, message_ids,
            )


async def mark_failed(target_id: int, error: str):
    async with pool().acquire() as conn:
        await conn.execute(
            "UPDATE post_targets SET status = 'failed', error = $2 WHERE id = $1",
            target_id, error[:500],
        )


async def fetch_due_to_delete():
    async with pool().acquire() as conn:
        return await conn.fetch(
            """
            SELECT pt.id AS target_id, pt.message_ids, c.chat_id
            FROM post_targets pt
            JOIN channels c ON c.id = pt.channel_id
            WHERE pt.status = 'published'
              AND pt.delete_at IS NOT NULL
              AND pt.delete_at <= now()
            """
        )


async def mark_deleted(target_id: int):
    async with pool().acquire() as conn:
        await conn.execute(
            "UPDATE post_targets SET status = 'deleted', deleted_at = now() WHERE id = $1",
            target_id,
        )


async def get_targets_for_post(post_id: int):
    async with pool().acquire() as conn:
        return await conn.fetch(
            """
            SELECT pt.id AS target_id, pt.status, pt.message_ids, pt.error, pt.publish_at,
                   c.chat_id, c.title
            FROM post_targets pt
            JOIN channels c ON c.id = pt.channel_id
            WHERE pt.post_id = $1
            ORDER BY pt.id
            """,
            post_id,
        )


# ---------- рассылка /post_all ----------

async def count_users() -> int:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) AS c FROM users")
        return row["c"]


async def get_all_user_tg_ids() -> list[int]:
    async with pool().acquire() as conn:
        rows = await conn.fetch("SELECT tg_id FROM users")
        return [r["tg_id"] for r in rows]


async def create_broadcast(
    admin_tg_id: int, text: str | None, entities_json: str | None,
    media_type: str, file_id: str | None, delete_after_hours: int | None,
) -> int:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO broadcasts (admin_tg_id, text, entities_json, media_type, file_id, delete_after_hours)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            admin_tg_id, text, entities_json, media_type, file_id, delete_after_hours,
        )
        return row["id"]


async def create_broadcast_targets(broadcast_id: int, tg_ids: list[int]):
    async with pool().acquire() as conn:
        async with conn.transaction():
            for tg_id in tg_ids:
                await conn.execute(
                    "INSERT INTO broadcast_targets (broadcast_id, user_tg_id) VALUES ($1, $2)",
                    broadcast_id, tg_id,
                )


async def get_pending_broadcast_targets(broadcast_id: int):
    async with pool().acquire() as conn:
        return await conn.fetch(
            """
            SELECT id AS target_id, user_tg_id FROM broadcast_targets
            WHERE broadcast_id = $1 AND status = 'pending'
            ORDER BY id
            """,
            broadcast_id,
        )


async def mark_broadcast_sent(target_id: int, message_id: int, delete_after_hours: int | None):
    async with pool().acquire() as conn:
        if delete_after_hours:
            await conn.execute(
                """
                UPDATE broadcast_targets
                SET status = 'sent', message_id = $2, sent_at = now(),
                    delete_at = now() + ($3 * INTERVAL '1 hour')
                WHERE id = $1
                """,
                target_id, message_id, delete_after_hours,
            )
        else:
            await conn.execute(
                "UPDATE broadcast_targets SET status = 'sent', message_id = $2, sent_at = now() WHERE id = $1",
                target_id, message_id,
            )


async def mark_broadcast_failed(target_id: int, error: str):
    async with pool().acquire() as conn:
        await conn.execute(
            "UPDATE broadcast_targets SET status = 'failed', error = $2 WHERE id = $1",
            target_id, error[:500],
        )


async def fetch_broadcast_targets_due_to_delete():
    async with pool().acquire() as conn:
        return await conn.fetch(
            """
            SELECT id AS target_id, user_tg_id, message_id FROM broadcast_targets
            WHERE status = 'sent' AND delete_at IS NOT NULL AND delete_at <= now()
            """
        )


async def mark_broadcast_deleted(target_id: int):
    async with pool().acquire() as conn:
        await conn.execute(
            "UPDATE broadcast_targets SET status = 'deleted', deleted_at = now() WHERE id = $1",
            target_id,
        )
