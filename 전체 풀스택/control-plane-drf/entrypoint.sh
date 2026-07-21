#!/usr/bin/env sh
set -eu
attempt=0
max_attempts="${DB_CONNECT_RETRIES:-60}"
until python manage.py shell -c "from django.db import connection; c=connection.cursor(); c.execute('SELECT 1'); c.close()" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "Application database did not become ready after $max_attempts attempts" >&2
    exit 1
  fi
  sleep 2
done
python manage.py migrate --noinput
python manage.py bootstrap_internal_auth
python manage.py collectstatic --noinput || true
exec "$@"
