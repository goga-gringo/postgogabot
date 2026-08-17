from zoneinfo import ZoneInfo

from bot.config import TIMEZONE
from bot import db

# Небольшой список на выбор в Настройках. При желании можно добавить ещё —
# главное, чтобы имя было валидным IANA-идентификатором.
COMMON_TIMEZONES = [
    ("Europe/Moscow", {"ru": "Москва (UTC+3)", "en": "Moscow (UTC+3)"}),
    ("Asia/Yekaterinburg", {"ru": "Екатеринбург (UTC+5)", "en": "Yekaterinburg (UTC+5)"}),
    ("Europe/Minsk", {"ru": "Минск (UTC+3)", "en": "Minsk (UTC+3)"}),
    ("Asia/Almaty", {"ru": "Алматы (UTC+6)", "en": "Almaty (UTC+6)"}),
    ("Europe/Berlin", {"ru": "Берлин (UTC+1/+2)", "en": "Berlin (UTC+1/+2)"}),
    ("UTC", {"ru": "UTC", "en": "UTC"}),
]


async def get_user_tz_name(user_id: int) -> str:
    user = await db.get_user(user_id)
    if user and user["timezone"]:
        return user["timezone"]
    return TIMEZONE


async def get_user_tz(user_id: int) -> ZoneInfo:
    name = await get_user_tz_name(user_id)
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(TIMEZONE)
