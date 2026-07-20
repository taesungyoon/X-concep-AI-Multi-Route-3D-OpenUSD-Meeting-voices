#!/usr/bin/env bash
set -euo pipefail
ray start --head --port="${RAY_PORT:-6379}" --dashboard-host=0.0.0.0
