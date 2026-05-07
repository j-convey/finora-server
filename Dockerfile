FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install psycopg2 for Alembic's synchronous migrations (asyncpg is async-only)
RUN pip install --no-cache-dir psycopg2-binary

# startup.sh: run migrations then start the server
COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

# Ensure the uploads directory exists; the Docker volume will be mounted here.
RUN mkdir -p /app/uploads/avatars

CMD ["/startup.sh"]
