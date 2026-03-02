#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_MAIN="${BASE_DIR}/shadow_router.cpp"
BIN="${BASE_DIR}/shadow_runner"

echo "[build] compile shadow target..."
g++ -std=c++17 -O2 -Wall -Wextra -pedantic "${SRC_MAIN}" -o "${BIN}"

echo "[run] launch shadow target..."
set +e
"${BIN}"
CODE=$?
set -e

echo "[done] code: ${CODE}"
exit "${CODE}"
