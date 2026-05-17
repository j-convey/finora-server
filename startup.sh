#!/bin/sh
set -e

echo "⏳ Running database migrations..."
python -m app.scripts.apply_migrations
echo "✅ Migrations complete."

echo "⏳ Seeding demo database schema..."
python -m app.scripts.seed_demo
echo "✅ Demo database seeding complete."

exec uvicorn app.main:app --host 0.0.0.0 --port 8080
