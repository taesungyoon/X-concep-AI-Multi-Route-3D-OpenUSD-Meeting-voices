#!/usr/bin/env sh
set -eu
MAX_UPLOAD_MB="${MAX_UPLOAD_MB:-128}"
printf 'upload_max_filesize=%sM\npost_max_size=%sM\nmax_file_uploads=8\nmax_execution_time=0\ndefault_socket_timeout=7200\n' "$MAX_UPLOAD_MB" "$MAX_UPLOAD_MB" \
  > /usr/local/etc/php/conf.d/xconcep-uploads.ini
mkdir -p /var/www/html/storage
chown -R www-data:www-data /var/www/html/storage || true
exec "$@"
