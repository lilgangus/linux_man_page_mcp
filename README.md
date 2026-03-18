# Linux Man Page Inverted Index — MCP Server

An MCP (Model Context Protocol) server that enables AI coding assistants to answer **aggregate queries** over Linux man pages — questions like "list all functions that return EINTR" or "what functions are declared in `<sys/socket.h>`?"

LLMs cannot answer these reliably because they require exhaustive search across all documentation. This project solves that with structured parsing and inverted indices.

## How It Works

1. **Collect** Linux man pages from sections 2 (system calls) and 3 (library functions) via Docker.
2. **Parse** each page, extracting structured fields: error codes, thread-safety attributes, header files, descriptions, and related functions.
3. **Build inverted indices** mapping properties → functions (e.g., `EINTR → {read, write, select, poll, ...}`).
4. **Serve** the indices as tools via an MCP server so AI assistants can query them directly.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Collect man pages (requires Docker)
cd data && bash collect.sh && cd ..

# Build the inverted index
./build_index.sh

# Run the MCP server (stdio transport, for Claude Desktop / mcphost)
python3 server.py

# Or run with SSE transport for remote clients
python3 server.py --transport sse --port 8000
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `lookup_error_code(code)` | All functions that can return a given errno (e.g., `EINTR`, `ENOMEM`) |
| `lookup_header(header)` | All functions declared in a given header (e.g., `<sys/socket.h>`) |
| `lookup_attribute(attr)` | All functions with a given attribute (e.g., `MT-Safe`, `AS-Safe`) |

## Project Structure

```
linux-manpage-mcp/
├── server.py                  # MCP server exposing lookup tools
├── build_index.sh             # Build script for the inverted index
├── requirements.txt
├── parser/
│   ├── parse_manpages.py      # Parse man pages into structured records
│   └── build_index.py         # Build inverted indices from parsed data
├── data/
│   ├── collect.sh             # Docker-based man page collection
│   └── collect_man_pages.py   # Render man pages to plain text
├── models/
│   └── index.json             # Prebuilt inverted index (generated)
└── evaluation/                # A/B testing: MCP vs no-MCP debugging
    ├── ab_protocol.md         # Experiment protocol
    ├── ab_scoring.md          # Scoring rubric
    ├── ab_shared_prompt.md    # Shared prompt for both arms
    ├── shadow_router.cpp      # Test program with deliberate errno obfuscation
    ├── run_shadow_probe.sh    # Build & run the test binary
    ├── debug_analysis_mcp.md  # Analysis WITH MCP tools
    ├── debug_analysis_no_mcp.md  # Analysis WITHOUT MCP tools
    └── debugging_comparison_report.pdf
```

## Key Design Decisions

- **Not RAG.** This is a structured lookup problem, not a fuzzy retrieval problem. We need exhaustive, exact results — not approximate similarity matches.
- **Parse once, serve fast.** Man page parsing happens offline. The MCP server loads a prebuilt index and answers queries from memory.
- **Ground truth from the source.** The parsed data itself serves as ground truth for evaluation.

## Evaluation

The `evaluation/` directory contains an A/B test comparing LLM debugging performance with and without MCP tools. A C++ test program (`shadow_router.cpp`) deliberately obfuscates errno values; the experiment measures whether access to the MCP server's `lookup_error_code` tool helps the LLM identify the true root cause. See [evaluation/ab_protocol.md](evaluation/ab_protocol.md) for the full protocol and [evaluation/debugging_comparison_report.pdf](evaluation/debugging_comparison_report.pdf) for results.

## Tech Stack

- **Language:** Python 3.11+
- **MCP SDK:** [`mcp`](https://github.com/modelcontextprotocol/python-sdk) (FastMCP)
- **Index format:** JSON
- **Data source:** Linux man pages, sections 2 & 3 (2,276 pages)
