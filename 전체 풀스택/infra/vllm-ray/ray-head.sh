#!/usr/bin/env bash
set -euo pipefail
RAY_PORT="${RAY_PORT:-6379}"
DASHBOARD_PORT="${RAY_DASHBOARD_PORT:-8265}"
NODE_IP="${RAY_NODE_IP:?RAY_NODE_IP is required}"
ray stop --force || true
ray start --head --node-ip-address="$NODE_IP" --port="$RAY_PORT" --dashboard-host=0.0.0.0 --dashboard-port="$DASHBOARD_PORT" --block
