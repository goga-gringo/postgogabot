import json

from aiogram.types import MessageEntity


def serialize_entities(entities: list[MessageEntity] | None) -> str | None:
    """Сериализуем entities (bold/italic/links/custom_emoji и т.д.) в JSON-строку
    для хранения в БД. Работаем с сырыми entities, а не с HTML-разметкой —
    так надёжнее (нет риска экранирования тегов при повторном парсинге)."""
    if not entities:
        return None
    return json.dumps([e.model_dump(exclude_none=True) for e in entities])


def deserialize_entities(entities_json: str | None) -> list[MessageEntity] | None:
    if not entities_json:
        return None
    try:
        raw = json.loads(entities_json)
        return [MessageEntity(**item) for item in raw]
    except Exception:
        return None
