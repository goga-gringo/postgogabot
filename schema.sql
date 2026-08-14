-- Пользователи бота
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    tg_id BIGINT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Подключённые каналы (бот должен быть там админом)
CREATE TABLE IF NOT EXISTS channels (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(owner_id, chat_id)
);

-- Черновик/контент поста. text хранится как HTML (aiogram html_text) —
-- так сохраняются форматирование и premium-эмодзи (<tg-emoji emoji-id="...">)
CREATE TABLE IF NOT EXISTS posts (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT,
    media_type TEXT,        -- 'text' | 'photo' | 'video' | 'album'
    file_id TEXT,            -- используется для photo/video; для album — NULL
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Элементы альбома (media_type = 'album'), по порядку
CREATE TABLE IF NOT EXISTS post_media (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    position INT NOT NULL,
    media_type TEXT NOT NULL,  -- 'photo' | 'video'
    file_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_post_media_post ON post_media (post_id, position);

-- Конкретная публикация поста в конкретный канал: своё время, свой автоудалятор
CREATE TABLE IF NOT EXISTS post_targets (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    channel_id BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    publish_at TIMESTAMPTZ NOT NULL,
    delete_after_hours INT,        -- NULL = никогда не удалять
    status TEXT NOT NULL DEFAULT 'scheduled',  -- scheduled | published | deleted | failed
    message_ids BIGINT[],          -- одно сообщение = [id]; альбом = несколько id
    published_at TIMESTAMPTZ,
    delete_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_targets_pending_publish
    ON post_targets (publish_at) WHERE status = 'scheduled';

CREATE INDEX IF NOT EXISTS idx_targets_pending_delete
    ON post_targets (delete_at) WHERE status = 'published' AND delete_at IS NOT NULL;
