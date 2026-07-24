#!/usr/bin/env sh
set -eu
HOST="${CAD_AI_HOST:-127.0.0.1}"
PORT="${CAD_AI_PORT:-8080}"
php -S "${HOST}:${PORT}" -t public router.php
