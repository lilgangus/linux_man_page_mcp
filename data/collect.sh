#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

docker run --rm \
  -v "$SCRIPT_DIR":/data \
  debian:bookworm \
  bash -c "
    apt-get update -qq && \
    apt-get install -y -qq man-db manpages manpages-dev python3 && \
    python3 /data/collect_man_pages.py
  "
