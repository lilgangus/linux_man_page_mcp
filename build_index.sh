#!/usr/bin/env bash
# Build the inverted index from the collected man pages.
# Output: models/index.json
#
# Usage:
#   ./build_index.sh [--indent 2] [--output path/to/output.json]

set -euo pipefail
cd "$(dirname "$0")"   # always run from the project root

python3 -m parser.build_index "$@"
