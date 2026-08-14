-- Пользователи бота
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    tg_id BIGINT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Персональные настройки пользователя (необязательные, есть дефолты в коде)
ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS default_delete_after_hours INT;
-- id последнего "экранного" сообщения бота этому пользователю — чтобы удалять
-- его перед показом нового экрана и не плодить вереницу сообщений с мёртвыми кнопками
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_bot_message_id BIGINT;

-- Подключённые каналы (бот должен быть там админом)
CREATE TABLE IF NOT EXISTS channels (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(owner_id, chat_id)
);

-- Черновик/контент поста. text — обычный текст (без HTML), форматирование
-- и custom-эмодзи хранятся отдельно как сырые entities (entities_json) —
-- так надёжнее, чем HTML-разметка, и меньше риск, что Telegram что-то не так распарсит.
CREATE TABLE IF NOT EXISTS posts (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT,
    media_type TEXT,        -- 'text' | 'photo' | 'video' | 'album'
    file_id TEXT,            -- используется для photo/video; для album — NULL
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE posts ADD COLUMN IF NOT EXISTS entities_json TEXT;

-- Откуда скопировать оригинал при публикации (chat_id/message_id(s) в личке с ботом).
-- copyMessage/copyMessages сохраняют premium-эмодзи и любые другие entities как есть —
-- надёжнее, чем пересобирать сообщение через send* с ручными entities.
ALTER TABLE posts ADD COLUMN IF NOT EXISTS source_chat_id BIGINT;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS source_message_ids BIGINT[];
-- Если текст поста правили после создания (через "Мои посты") — оригинал в личке
-- уже не соответствует новому тексту, публикуем через пересборку (file_id + entities).
ALTER TABLE posts ADD COLUMN IF NOT EXISTS text_edited BOOLEAN NOT NULL DEFAULT false;

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
