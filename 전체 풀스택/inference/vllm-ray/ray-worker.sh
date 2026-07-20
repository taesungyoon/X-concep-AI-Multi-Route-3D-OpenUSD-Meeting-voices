#!/usr/bin/env bash
set -euo pipefail
: "${RAY_HEAD_ADDRESS:?RAY_HEAD_ADDRESS is required}"
ray start --address="$RAY_HEAD_ADDRESS"
