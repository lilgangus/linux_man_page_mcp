#!/usr/bin/env python3
"""Linux man-page MCP server.

Exposes three tools over the Model Context Protocol so that any MCP-compatible
AI assistant can answer aggregate queries about Linux system calls and library
functions:

    lookup_error_code(code)   – functions that can return a given errno
    lookup_header(header)     – functions declared in a given #include header
    lookup_attribute(attr)    – functions with a given thread-safety attribute

The server loads models/index.json at startup (built by parser/build_index.py)
and answers queries entirely from memory — no file I/O per request.

Usage (stdio transport, for Claude Desktop / mcphost):
    python3 server.py

Usage (HTTP/SSE transport, for browser-based or remote clients):
    python3 server.py --transport sse --port 8000
"""

import argparse
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from parser.build_index import load_index

# ── Load index ────────────────────────────────────────────────────────────────

_INDEX_PATH = Path(__file__).resolve().parent / "models" / "index.json"

if not _INDEX_PATH.exists():
    sys.exit(
        f"Index not found at {_INDEX_PATH}.\n"
        "Run ./build_index.sh first to build it."
    )

_index = load_index(_INDEX_PATH)

# ── MCP server ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "linux-manpages",
    instructions=(
        "Use these tools to answer aggregate questions about Linux system calls "
        "and library functions. lookup_error_code, lookup_header, and "
        "lookup_attribute each return an exhaustive, exact list — prefer them "
        "over guessing from training data."
    ),
)


@mcp.tool()
def lookup_error_code(code: str) -> list[dict]:
    """Return all Linux functions that can return a given errno value.

    Args:
        code: The errno name, e.g. "EINTR", "ENOMEM", "EAGAIN".
              Case-insensitive.

    Returns:
        List of {name, section, page, description} dicts, sorted by name.
        Empty list if no functions document that error code.
    """
    return _index["by_error_code"].get(code.upper(), [])


@mcp.tool()
def lookup_header(header: str) -> list[dict]:
    """Return all Linux functions declared in a given C header file.

    Args:
        header: The header name, e.g. "<unistd.h>", "<sys/socket.h>".
                Angle brackets are required.

    Returns:
        List of {name, section, page, description} dicts, sorted by name.
        Empty list if the header is not found.
    """
    return _index["by_header"].get(header, [])


@mcp.tool()
def lookup_attribute(attr: str) -> list[dict]:
    """Return all Linux functions with a given thread-safety (or other) attribute.

    Common attribute values:
        MT-Safe       – fully thread-safe
        MT-Unsafe     – not thread-safe
        MT-Safe locale, MT-Safe race:stream, … – thread-safe with caveats
        AS-Safe       – async-signal-safe
        AC-Safe       – async-cancel-safe

    Querying a base value like "MT-Safe" returns ALL functions that are
    MT-Safe (including those with qualifiers like "MT-Safe locale").

    Args:
        attr: The attribute value, e.g. "MT-Safe", "MT-Unsafe", "AS-Safe".
              Case-sensitive.

    Returns:
        List of {name, section, page, description} dicts, sorted by name.
        Empty list if no functions carry that attribute.
    """
    return _index["by_attribute"].get(attr, [])


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Linux man-page MCP server.")
    ap.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport to use (default: stdio)",
    )
    ap.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000)",
    )
    args = ap.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
