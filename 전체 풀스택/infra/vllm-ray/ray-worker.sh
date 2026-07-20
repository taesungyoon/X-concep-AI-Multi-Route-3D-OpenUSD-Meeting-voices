#!/usr/bin/env bash
set -euo pipefail
HEAD_IP="${RAY_HEAD_IP:?RAY_HEAD_IP is required}"
RAY_PORT="${RAY_PORT:-6379}"
NODE_IP="${RAY_NODE_IP:?RAY_NODE_IP is required}"
ray stop --force || true
ray start --address="$HEAD_IP:$RAY_PORT" --node-ip-address="$NODE_IP" --block
