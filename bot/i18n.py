from bot import db

DEFAULT_LANG = "ru"
LANGUAGES = ["ru", "en"]

T = {
    # ---------- общее / меню ----------
    "menu.create": {"ru": "📝 Создать пост", "en": "📝 Create post"},
    "menu.channels": {"ru": "📢 Мои каналы", "en": "📢 My channels"},
    "menu.posts": {"ru": "📋 Мои посты", "en": "📋 My posts"},
    "menu.settings": {"ru": "⚙️ Настройки", "en": "⚙️ Settings"},
    "menu.text": {"ru": "Главное меню — выбирай раздел внизу 👇", "en": "Main menu — pick a section below 👇"},

    "btn.next": {"ru": "➡️ Далее", "en": "➡️ Next"},
    "btn.cancel": {"ru": "✖️ Отмена", "en": "✖️ Cancel"},
    "btn.select_all": {"ru": "✅ Во все", "en": "✅ Select all"},
    "btn.deselect_all": {"ru": "🚫 Снять со всех", "en": "🚫 Deselect all"},
    "btn.never_delete": {"ru": "Не удалять", "en": "Never delete"},
    "btn.publish_now": {"ru": "🚀 Опубликовать сейчас", "en": "🚀 Publish now"},
    "btn.in_1h": {"ru": "🕐 Через 1 час", "en": "🕐 In 1 hour"},
    "btn.in_3h": {"ru": "🕒 Через 3 часа", "en": "🕒 In 3 hours"},
    "btn.custom_time": {"ru": "📅 Указать время вручную", "en": "📅 Set custom time"},
    "btn.edit_link_buttons": {"ru": "🔗 Изменить кнопки-ссылки", "en": "🔗 Edit link buttons"},
    "btn.add_link_buttons": {"ru": "🔗 Добавить кнопку-ссылку", "en": "🔗 Add link button"},
    "btn.back": {"ru": "🔙 Назад", "en": "🔙 Back"},
    "btn.home": {"ru": "🏠 Главное меню", "en": "🏠 Main menu"},
    "btn.add_channel": {"ru": "➕ Добавить канал", "en": "➕ Add channel"},
    "btn.default_delete_hours": {"ru": "По умолчанию: {h}ч", "en": "Default: {h}h"},
    "btn.default_never": {"ru": "По умолчанию: не удалять", "en": "Default: never delete"},
    "btn.edit_text": {"ru": "✏️ Изменить текст", "en": "✏️ Edit text"},
    "btn.edit_buttons": {"ru": "🔗 Изменить кнопки", "en": "🔗 Edit buttons"},
    "btn.edit_media": {"ru": "🖼 Заменить медиа", "en": "🖼 Replace media"},
    "btn.delete_post": {"ru": "🗑 Удалить пост", "en": "🗑 Delete post"},
    "btn.delete_everywhere": {"ru": "🗑 Удалить везде ({n})", "en": "🗑 Delete everywhere ({n})"},
    "btn.only_channel": {"ru": "📍 Только «{title}»", "en": "📍 Only \u00ab{title}\u00bb"},
    "btn.back_short": {"ru": "⬅️ Назад", "en": "⬅️ Back"},
    "btn.lang_ru": {"ru": "🇷🇺 Русский", "en": "🇷🇺 Russian"},
    "btn.lang_en": {"ru": "🇬🇧 English", "en": "🇬🇧 English"},
    "btn.silent_off": {"ru": "🔕 Без звука", "en": "🔕 Silent"},
    "btn.silent_on": {"ru": "🔔 Со звуком", "en": "🔔 With sound"},
    "btn.delete_from_comments": {
        "ru": "Удалить из комментариев",
        "en": "Delete from comments",
    },

    # ---------- /start ----------
    "start.choose_language": {
        "ru": "Привет! Для начала выбери язык интерфейса:",
        "en": "Hi! First, choose your interface language:",
    },
    "start.welcome": {
        "ru": (
            "Привет! Я планировщик постов для твоих Telegram-каналов.\n\n"
            "Как пользоваться:\n"
            "1️⃣ «📢 Мои каналы» → добавь канал (сначала сделай меня админом канала с правами "
            "публикации, редактирования и удаления сообщений)\n"
            "2️⃣ «📝 Создать пост» → пришли текст, фото, видео или альбом\n"
            "3️⃣ Выбери, в какие каналы постить (можно сразу несколько), когда удалить "
            "и когда опубликовать\n\n"
            "Меню внизу — основные разделы. «📋 Мои посты» — там же редактирование текста "
            "(в т.ч. уже опубликованных постов), «⚙️ Настройки» — часовой пояс, язык и "
            "автоудаление по умолчанию."
        ),
        "en": (
            "Hi! I'm a post scheduler for your Telegram channels.\n\n"
            "How to use:\n"
            "1️⃣ \u00ab📢 My channels\u00bb → add a channel (first make me an admin there with "
            "posting, editing and deleting rights)\n"
            "2️⃣ \u00ab📝 Create post\u00bb → send text, photo, video or an album\n"
            "3️⃣ Choose which channels to post to (several at once works), when to delete "
            "and when to publish\n\n"
            "The menu below has the main sections. \u00ab📋 My posts\u00bb — edit text there "
            "(even for already published posts), \u00ab⚙️ Settings\u00bb — timezone, language "
            "and default auto-delete."
        ),
    },
    "start.cancelled": {"ru": "Отменено.", "en": "Cancelled."},

    # ---------- каналы ----------
    "channels.add_instructions": {
        "ru": (
            "{prefix}Чтобы подключить канал:\n\n"
            "1. Добавь меня в канал как администратора с правами:\n"
            "   • Публикация сообщений\n"
            "   • Редактирование сообщений других пользователей\n"
            "   • Удаление сообщений\n\n"
            "2. Опубликуй в канале сообщение с этим кодом (я сам его удалю):\n\n<code>{code}</code>\n\n"
            "Код действует 10 минут."
        ),
        "en": (
            "{prefix}To connect a channel:\n\n"
            "1. Add me to the channel as admin with rights:\n"
            "   • Post messages\n"
            "   • Edit other users' messages\n"
            "   • Delete messages\n\n"
            "2. Post any message with this code in the channel (I'll delete it myself):\n\n<code>{code}</code>\n\n"
            "The code is valid for 10 minutes."
        ),
    },
    "channels.no_channels": {"ru": "Пока нет подключённых каналов.\n\n", "en": "No channels connected yet.\n\n"},
    "channels.list_header": {"ru": "Твои каналы:", "en": "Your channels:"},
    "channels.removed": {"ru": "Канал отключён.\n\nТвои каналы:", "en": "Channel disconnected.\n\nYour channels:"},
    "channels.removed_none_left": {
        "ru": "Канал отключён. Больше подключённых каналов нет.",
        "en": "Channel disconnected. No channels left.",
    },
    "channels.connected": {"ru": "✅ Канал «{title}» подключён!{note}", "en": "✅ Channel \u00ab{title}\u00bb connected!{note}"},
    "channels.no_edit_right": {
        "ru": (
            "\n⚠️ Нет права «Редактирование сообщений других пользователей» — "
            "live-правка текста уже опубликованных постов работать не будет."
        ),
        "en": (
            "\n⚠️ No \"Edit other users' messages\" right — live-editing text of "
            "already published posts won't work."
        ),
    },
    "channels.forward_not_channel": {
        "ru": (
            "Не могу определить исходный канал по этой пересылке "
            "(Telegram скрывает эту информацию для репостов и части пересланных сообщений).\n\n"
            "Пересылка вообще ненадёжна для подключения канала — используй способ через код: "
            "«📢 Мои каналы» → «➕ Добавить канал»."
        ),
        "en": (
            "Can't determine the source channel from this forward "
            "(Telegram hides this info for reposts and some forwarded messages).\n\n"
            "Forwarding isn't reliable for connecting a channel anyway — use the code method: "
            "\u00ab📢 My channels\u00bb → \u00ab➕ Add channel\u00bb."
        ),
    },
    "channels.forward_not_member": {
        "ru": (
            "Не вижу себя участником этого канала.\n\n"
            "Обычно помогает:\n"
            "1. Проверь, что я добавлен в Администраторы канала\n"
            "2. Если только что добавил права — подожди 20-30 секунд\n"
            "3. Пришли в канал новое сообщение и перешли мне именно его"
        ),
        "en": (
            "I don't see myself as a member of this channel.\n\n"
            "Usually helps to:\n"
            "1. Check that I'm added to channel Admins\n"
            "2. If you just granted rights — wait 20-30 seconds\n"
            "3. Post a new message in the channel and forward that one to me"
        ),
    },
    "channels.forward_check_error": {"ru": "Не удалось проверить права в канале: {error}", "en": "Couldn't check channel rights: {error}"},
    "channels.forward_not_admin": {
        "ru": (
            "Я не администратор этого канала (или не хватает прав публикации/удаления). "
            "Добавь мне права и перешли сообщение ещё раз."
        ),
        "en": (
            "I'm not an admin of this channel (or missing post/delete rights). "
            "Grant me the rights and forward the message again."
        ),
    },

    # ---------- Мои посты ----------
    "myposts.none": {
        "ru": "Постов пока нет. Пришли текст/фото/видео, чтобы создать первый.",
        "en": "No posts yet. Send text/photo/video to create the first one.",
    },
    "myposts.header": {"ru": "Твои последние посты:", "en": "Your recent posts:"},
    "myposts.page_indicator": {"ru": "Страница {page}/{total}", "en": "Page {page}/{total}"},
    "myposts.not_found": {"ru": "Пост не найден", "en": "Post not found"},
    "post.deleted_everywhere": {"ru": "Пост #{id} удалён отовсюду.", "en": "Post #{id} deleted everywhere."},
    "post.no_text": {"ru": "(без текста)", "en": "(no text)"},
    "post.channels_header": {"ru": "Каналы:", "en": "Channels:"},
    "status.scheduled": {"ru": "запланирован", "en": "scheduled"},
    "status.published": {"ru": "опубликован", "en": "published"},
    "status.deleted": {"ru": "удалён", "en": "deleted"},
    "status.failed": {"ru": "ошибка", "en": "failed"},
    "post.at": {"ru": "в", "en": "at"},

    "edittext.hint_media": {
        "ru": "Только медиа-подпись, само фото/видео менять нельзя.",
        "en": "Only the caption — the photo/video itself can't be changed.",
    },
    "edittext.hint_text": {"ru": "Это текстовый пост целиком.", "en": "This is a text-only post."},
    "edittext.prompt": {
        "ru": "Пришли новый текст поста (форматирование сохранится).\n{hint}\n\n/cancel — отменить",
        "en": "Send new post text (formatting is preserved).\n{hint}\n\n/cancel — cancel",
    },
    "edittext.updated": {
        "ru": "✅ Текст в базе обновлён.\nУже опубликованные посты обновлены: {updated}.",
        "en": "✅ Text updated in the database.\nAlready published posts updated: {updated}.",
    },
    "edittext.failed": {"ru": "\n⚠️ Не удалось обновить {failed} шт.:\n{errors}", "en": "\n⚠️ Failed to update {failed}:\n{errors}"},
    "edittext.scheduled_note": {
        "ru": "\n\nЗапланированные, ещё не опубликованные посты выйдут уже с новым текстом.",
        "en": "\n\nScheduled, not-yet-published posts will go out with the new text.",
    },

    "delete.where": {"ru": "Где удалить пост?", "en": "Where should I delete the post?"},
    "delete.nowhere_active": {"ru": "Пост уже нигде не активен.", "en": "The post isn't active anywhere anymore."},
    "delete.done": {"ru": "🗑 Удалено: {n} шт.", "en": "🗑 Deleted: {n}."},

    "editbuttons.current_header": {"ru": "<b>Текущие кнопки:</b>", "en": "<b>Current buttons:</b>"},
    "editbuttons.none": {"ru": "(кнопок пока нет)", "en": "(no buttons yet)"},
    "editbuttons.not_for_album": {
        "ru": "У альбомов кнопок не бывает — ограничение Telegram.",
        "en": "Albums can't have buttons — Telegram limitation.",
    },
    "editbuttons.prompt": {
        "ru": (
            "Пришли новые кнопки — они <b>полностью заменят</b> текущие (не добавятся к ним).\n"
            "Формат — как при создании поста: <code>Текст - ссылка</code> на строку, "
            "несколько в один ряд — через <code>|</code>.\n"
            "Количество может быть любым: было 2 — станет хоть 1, хоть 5.\n"
            "Чтобы убрать кнопки совсем — пришли <code>-</code>\n\n"
            "/cancel — отменить, оставить как есть"
        ),
        "en": (
            "Send new buttons — they'll <b>fully replace</b> the current ones (not added to them).\n"
            "Format — same as when creating a post: <code>Text - link</code> per line, "
            "several in one row — separated by <code>|</code>.\n"
            "Count can be anything: had 2 — can become 1 or 5.\n"
            "To remove all buttons — send <code>-</code>\n\n"
            "/cancel — cancel, keep as is"
        ),
    },
    "editbuttons.updated": {
        "ru": "✅ Кнопки обновлены.\nУже опубликованные посты обновлены: {updated}.",
        "en": "✅ Buttons updated.\nAlready published posts updated: {updated}.",
    },
    "editbuttons.failed": {"ru": "\n⚠️ Не удалось обновить {failed} шт.", "en": "\n⚠️ Failed to update {failed}."},

    "editmedia.not_supported": {
        "ru": "Замена медиа работает только для фото/видео/альбома (не для текстовых постов).",
        "en": "Media replacement only works for photo/video/album posts (not text-only).",
    },
    "editmedia.prompt": {
        "ru": (
            "Пришли новое фото или видео — заменит текущее медиа везде, включая уже "
            "опубликованные посты. Текст и кнопки останутся прежними.\n\n"
            "/cancel — отменить, оставить как есть"
        ),
        "en": (
            "Send a new photo or video — it'll replace the current media everywhere, "
            "including already published posts. Text and buttons stay the same.\n\n"
            "/cancel — cancel, keep as is"
        ),
    },
    "editmedia.album_prompt": {
        "ru": (
            "Пришли новый альбом (несколько фото/видео разом, можно и одно) — медиа "
            "заменится. В карточке поста («📋 Мои посты») сами фото/видео альбома не "
            "показываются в превью — только текст и статус, чтобы не захламлять экран "
            "кучей картинок. На саму замену это не влияет, применится корректно.\n\n"
            "/cancel — отменить, оставить как есть"
        ),
        "en": (
            "Send a new album (several photos/videos at once, or just one) — the media "
            "will be replaced. The post card (\u00ab📋 My posts\u00bb) doesn't preview the "
            "album's actual photos/videos — just text and status, to avoid clutter. This "
            "doesn't affect the replacement itself, it applies correctly.\n\n"
            "/cancel — cancel, keep as is"
        ),
    },
    "editmedia.updated": {
        "ru": "✅ Медиа заменено.\nУже опубликованные посты обновлены: {updated}.",
        "en": "✅ Media replaced.\nAlready published posts updated: {updated}.",
    },
    "editmedia.failed": {"ru": "\n⚠️ Не удалось обновить {failed} шт.", "en": "\n⚠️ Failed to update {failed}."},
    "editmedia.mismatch": {
        "ru": "\n⚠️ У {n} шт. другое число фото/видео, чем было — Telegram не даёт менять размер альбома в готовом посте, эти остались без изменений.",
        "en": "\n⚠️ {n} have a different item count than before — Telegram doesn't allow resizing an album in a published post, those were left unchanged.",
    },

    # ---------- создание поста ----------
    "newpost.no_channels": {
        "ru": "Сначала подключи хотя бы один канал: «📢 Мои каналы»",
        "en": "First connect at least one channel: \u00ab📢 My channels\u00bb",
    },
    "newpost.choose_channels": {
        "ru": "В какие каналы постим? Отметь один или несколько:",
        "en": "Which channels should I post to? Pick one or several:",
    },
    "newpost.select_at_least_one": {"ru": "Выбери хотя бы один канал!", "en": "Pick at least one channel!"},
    "newpost.channels_selected_send_content": {
        "ru": "Каналы выбраны ✅\n\nТеперь пришли текст, фото, видео или альбом — это станет содержимым поста.",
        "en": "Channels selected ✅\n\nNow send text, photo, video or an album — that'll be the post content.",
    },
    "newpost.channels_selected_using_pending": {
        "ru": "Каналы выбраны ✅ Использую пост, который ты уже прислал.",
        "en": "Channels selected ✅ Using the post you already sent.",
    },
    "newpost.pending_prompt": {
        "ru": "Пост принят — жду выбор каналов.\nОтметь галочками и жми «➡️ Далее».",
        "en": "Post received — waiting for channel selection.\nCheck the boxes and hit \u00ab➡️ Next\u00bb.",
    },
    "newpost.pending_album_prompt": {
        "ru": "Альбом из {n} медиафайлов принят — жду выбор каналов.\nОтметь галочками и жми «➡️ Далее».",
        "en": "Album of {n} media files received — waiting for channel selection.\nCheck the boxes and hit \u00ab➡️ Next\u00bb.",
    },
    "newpost.album_received": {"ru": "Альбом из {n} медиафайлов принят.", "en": "Album of {n} media files received."},
    "newpost.stray_reminder": {
        "ru": "Чтобы создать пост, сначала нажми «📝 Создать пост» внизу — там сперва выбираем каналы, потом присылаем контент.",
        "en": "To create a post, first tap \u00ab📝 Create post\u00bb below — pick channels first, then send content.",
    },
    "newpost.delete_after_prompt": {"ru": "Когда удалить пост после публикации?", "en": "When should the post be deleted after publishing?"},
    "newpost.delete_marker": {"ru": "Отметка удаления: {label}.", "en": "Auto-delete: {label}."},
    "newpost.delete_never": {"ru": "не удалять", "en": "never"},
    "newpost.delete_in_hours": {"ru": "удалить через {h}ч", "en": "delete after {h}h"},
    "newpost.album_preview_note": {
        "ru": "👆 Так будет выглядеть альбом (кнопки под альбомом Telegram не поддерживает).\nКогда публикуем?",
        "en": "👆 This is how the album will look (Telegram doesn't support buttons under albums).\nWhen do we publish?",
    },
    "newpost.custom_time_prompt": {
        "ru": "Напиши дату и время публикации в формате:\n<code>31.12.2026 15:30</code>",
        "en": "Send the publish date and time as:\n<code>31.12.2026 15:30</code>",
    },
    "newpost.custom_time_recent_header": {"ru": "Ваши варианты:", "en": "Your recent picks:"},
    "newpost.custom_time_tz_line": {
        "ru": "Часовой пояс: {tz} (поменять — в ⚙️ Настройках)",
        "en": "Timezone: {tz} (change it in ⚙️ Settings)",
    },
    "newpost.custom_time_bad_format": {"ru": "Не понял формат. Пример: 31.12.2026 15:30", "en": "Didn't understand the format. Example: 31.12.2026 15:30"},
    "newpost.custom_time_past": {"ru": "Это время уже в прошлом. Введи время в будущем.", "en": "That time is already in the past. Enter a future time."},
    "newpost.link_buttons_prompt": {
        "ru": (
            "Пришли кнопки-ссылки под постом. Формат — одна кнопка на строку:\n"
            "<code>Текст - ссылка</code>\n"
            "Несколько кнопок в один ряд — через <code>|</code>\n\n"
            "Например:\n"
            "<code>Подписаться - t.me/durov</code>\n"
            "<code>Сайт - https://example.com | Чат - https://t.me/chat</code>"
        ),
        "en": (
            "Send link buttons for the post. One button per line:\n"
            "<code>Text - link</code>\n"
            "Several buttons in one row — separate with <code>|</code>\n\n"
            "Example:\n"
            "<code>Subscribe - t.me/durov</code>\n"
            "<code>Website - https://example.com | Chat - https://t.me/chat</code>"
        ),
    },
    "newpost.link_buttons_bad_format": {
        "ru": "{hint}Формат: <code>Текст - ссылка</code>. Ссылка должна начинаться с http://, https:// или tg://. Попробуй ещё раз, или «🔙 Назад».",
        "en": "{hint}Format: <code>Text - link</code>. The link must start with http://, https:// or tg://. Try again, or \u00ab🔙 Back\u00bb.",
    },
    "newpost.link_buttons_bad_part": {"ru": "Не понял часть: <code>{part}</code>\n", "en": "Didn't understand this part: <code>{part}</code>\n"},
    "newpost.edit_text_prompt": {
        "ru": "Пришли новый текст поста (форматирование и premium-эмодзи сохранятся).\n\n/cancel — отменить, оставить как есть",
        "en": "Send new post text (formatting and premium emoji are preserved).\n\n/cancel — cancel, keep as is",
    },
    "newpost.edit_media_prompt": {
        "ru": "Пришли новое фото или видео — заменит текущее в этом черновике. Текст и кнопки останутся прежними.\n\n/cancel — отменить, оставить как есть",
        "en": "Send a new photo or video — it'll replace the current one in this draft. Text and buttons stay the same.\n\n/cancel — cancel, keep as is",
    },
    "newpost.edit_media_album_prompt": {
        "ru": (
            "Пришли новый альбом (несколько фото/видео разом, можно и одно) — заменит текущий "
            "в этом черновике. Текст и кнопки останутся прежними.\n\n"
            "/cancel — отменить, оставить как есть"
        ),
        "en": (
            "Send a new album (several photos/videos at once, or just one) — it'll replace the "
            "current one in this draft. Text and buttons stay the same.\n\n"
            "/cancel — cancel, keep as is"
        ),
    },
    "newpost.finalize": {
        "ru": (
            "✅ Готово!\n\n"
            "Каналы: {channels}\n"
            "Публикация: {when}\n"
            "Удаление: {delete_label}\n"
            "Звук: {sound_label}\n\n"
            "Изменить текст поста позже можно в разделе «📋 Мои посты»"
        ),
        "en": (
            "✅ Done!\n\n"
            "Channels: {channels}\n"
            "Publishing: {when}\n"
            "Auto-delete: {delete_label}\n"
            "Sound: {sound_label}\n\n"
            "You can edit the post text later in \u00ab📋 My posts\u00bb"
        ),
    },
    "newpost.finalize_now": {"ru": "сейчас", "en": "now"},
    "newpost.sound_off": {"ru": "выключен (без уведомления)", "en": "off (no notification)"},
    "newpost.sound_on": {"ru": "включён", "en": "on"},

    # ---------- настройки ----------
    "settings.header": {
        "ru": (
            "⚙️ Настройки\n\n"
            "Часовой пояс — используется для ручного ввода времени публикации.\n"
            "Автоудаление по умолчанию — какая опция будет отмечена звёздочкой ⭐ "
            "при создании поста (можно всегда выбрать другую вручную).\n"
            "Язык — язык интерфейса бота."
        ),
        "en": (
            "⚙️ Settings\n\n"
            "Timezone — used for manually entering the publish time.\n"
            "Default auto-delete — which option gets a ⭐ when creating a post "
            "(you can always pick a different one manually).\n"
            "Language — the bot's interface language."
        ),
    },
}


def t(lang: str | None, key: str, **kwargs) -> str:
    lang = lang if lang in T.get(key, {}) else DEFAULT_LANG
    template = T.get(key, {}).get(lang) or key
    return template.format(**kwargs) if kwargs else template


def variants(key: str) -> set[str]:
    """Все переводы данного ключа — чтобы матчить reply-кнопку независимо
    от того, на каком языке она сейчас подписана у конкретного пользователя."""
    return set(T.get(key, {}).values())


async def get_user_lang(user_id: int) -> str:
    user = await db.get_user(user_id)
    if user and user["language"] in LANGUAGES:
        return user["language"]
    return DEFAULT_LANG
