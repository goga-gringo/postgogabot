import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        present = sorted(k for k in os.environ.keys() if not k.startswith("_"))
        raise RuntimeError(
            f"Переменная окружения '{name}' не задана.\n"
            f"Проверь, что она добавлена в Variables ИМЕННО этого сервиса на Railway "
            f"(не в сервисе Postgres) и что имя написано без опечаток.\n"
            f"Сейчас в окружении видно {len(present)} переменных: {present}"
        )
    return value


BOT_TOKEN = _require("BOT_TOKEN")

# Railway подставляет DATABASE_URL сам, если подключить Postgres плагин.
DATABASE_URL = _require("DATABASE_URL")

# Как часто (в секундах) воркеры проверяют, что пора публиковать/удалять
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "20"))

# Часовой пояс, в котором пользователь вводит время публикации вручную
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Moscow")

# Через сколько дней физически удалять старые посты из БД (сами, без активных
# запланированных публикаций) — освобождает место, история не копится вечно
POST_RETENTION_DAYS = int(os.environ.get("POST_RETENTION_DAYS", "30"))

# Как часто (в секундах) проверять и чистить старые посты — не нужно часто,
# раз в несколько часов достаточно
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", str(6 * 3600)))

