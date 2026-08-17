# Простой однослойный образ — бот лёгкий, ничего сложного не нужно.
FROM python:3.12-slim

WORKDIR /app

# Системные зависимости для сборки некоторых Python-пакетов (asyncpg и т.п.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект: bot/, schema.sql и т.д.
COPY . .

# Бот не слушает HTTP — это фоновый воркер на long-polling к Telegram.
# На Northflank выбирай тип сервиса без HTTP-порта / health-check по порту,
# иначе платформа может решить, что сервис "не поднялся".
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "bot.main"]
