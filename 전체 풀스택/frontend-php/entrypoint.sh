#!/usr/bin/env sh
set -eu
mkdir -p /var/www/html/storage
chown -R www-data:www-data /var/www/html/storage || true
exec "$@"
