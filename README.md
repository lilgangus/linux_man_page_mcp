# Linux Man Page Inverted Index — MCP Server

## Project Goal

Build an MCP (Model Context Protocol) server that enables AI coding assistants to answer **aggregate queries** over Linux man pages — questions like "list all functions that return EINTR" or "what functions are declared in `<sys/socket.h>`?" LLMs cannot answer these reliably because they require exhaustive search across all documentation. This project solves that with structured parsing and inverted indices.

## How It Works

1. **Parse** Linux man pages from sections 2 (system calls) and 3 (library functions), extracting structured fields: error codes, attributes, header files, return types, related functions.
2. **Build inverted indices** mapping properties → functions (e.g., `EINTR → {read, write, select, poll, ...}`).
3. **Expose** the indices as tools via an MCP server so AI assistants can query them directly.
4. **Evaluate** against LLM-only, LLM + web search, and Google baselines using auto-generated benchmarks measuring recall and precision.

## Tech Stack

- **Language:** Python
- **MCP SDK:** `mcp` (Python SDK, using `FastMCP`)
- **Data storage:** JSON or SQLite for the prebuilt index
- **Input data:** Raw man pages from Linux sections 2 and 3 (groff/troff format)

## Project Structure

```
linux-manpage-mcp/
├── parser/
│   ├── parse_manpages.py      # Parse man pages into structured data
│   └── build_index.py         # Build inverted indices from parsed data
├── data/
│   └── index.json             # Prebuilt inverted index
├── server.py                  # MCP server exposing lookup tools
└── eval/
    └── benchmark.py           # Evaluation against LLM baselines
```

## MCP Tools to Expose

- `lookup_error_code(code)` — Returns all functions that can return a given errno (e.g., EINTR, ENOMEM).
- `lookup_header(header)` — Returns all functions declared in a given header file.
- `lookup_attribute(attr)` — Returns all functions with a given attribute (e.g., async-signal-safe, thread-safe).

## Key Design Decisions

- **Not RAG.** This is a structured lookup problem, not a fuzzy retrieval problem. We need exhaustive, exact results — not approximate similarity matches.
- **Parse once, serve fast.** Man page parsing happens offline. The MCP server loads a prebuilt index and answers queries from memory.
- **Ground truth from the source.** Evaluation benchmarks are auto-generated from the parsed data itself, ensuring correctness.
