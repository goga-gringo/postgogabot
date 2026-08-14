import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]

# Railway подставляет DATABASE_URL сам, если подключить Postgres плагин.
DATABASE_URL = os.environ["DATABASE_URL"]

# Как часто (в секундах) воркеры проверяют, что пора публиковать/удалять
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "20"))

# Часовой пояс, в котором пользователь вводит время публикации вручную
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Moscow")
