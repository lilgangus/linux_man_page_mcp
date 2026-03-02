#!/usr/bin/env python3
"""Build inverted indices from parsed man page records.

Three indices are produced:

  by_error_code   errno name  → [FuncEntry, ...]
  by_header       #include    → [FuncEntry, ...]
  by_attribute    attr value  → [FuncEntry, ...]

FuncEntry = {"name": str, "section": str, "page": str, "description": str}

For `by_error_code` and `by_header`, every function name listed in a page's
NAME section is associated with all of that page's error codes / headers.

For `by_attribute`, entries come directly from the ATTRIBUTES table; each
interface name is stored under both its *exact* value (e.g. "MT-Safe locale")
and its *base* value (first token, e.g. "MT-Safe"), so that a query for
"MT-Safe" returns all MT-Safe functions regardless of qualifiers.

Output: models/index.json  (or a path of your choice)

Usage:
    python -m parser.build_index [--output FILE] [--indent N]
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from parser.parse_manpages import DATA_DIR, ManPageRecord, iter_man_pages

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "models" / "index.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

# Strip trailing "()" from ATTRIBUTES interface names like "pthread_create()".
_RE_IFACE_PARENS = re.compile(r"\(\s*\)$")


def _strip_iface(name: str) -> str:
    """Remove trailing () from an interface name."""
    return _RE_IFACE_PARENS.sub("", name).strip()


def _base_attr(value: str) -> str:
    """Return the first token of an attribute value.

    "MT-Safe locale" → "MT-Safe"
    "MT-Unsafe race:drand48" → "MT-Unsafe"
    "AS-Safe" → "AS-Safe"
    """
    return value.split()[0] if value else value


# ── Core builder ──────────────────────────────────────────────────────────────

def build_index(records: Iterable[ManPageRecord]) -> dict:
    """Build inverted indices from *records* and return a serialisable dict.

    The returned dict has the shape::

        {
          "by_error_code": { "EINTR": [FuncEntry, ...], ... },
          "by_header":     { "<unistd.h>": [FuncEntry, ...], ... },
          "by_attribute":  { "MT-Safe": [FuncEntry, ...], ... },
          "meta":          { "total_pages": int, "built_at": str, ... },
        }

    Entries within each list are sorted by (name, section) and deduplicated so
    that the same (name, section) pair never appears twice under one key.
    """
    # Intermediate storage: index_key → {(name, section): FuncEntry}
    # Using a nested dict keyed by (name, section) gives O(1) deduplication.
    ec_map: dict[str, dict[tuple, dict]] = defaultdict(dict)
    hdr_map: dict[str, dict[tuple, dict]] = defaultdict(dict)
    attr_map: dict[str, dict[tuple, dict]] = defaultdict(dict)

    total = 0

    for rec in records:
        total += 1

        # ── by_error_code and by_header ───────────────────────────────────────
        # All function names on the page share the same headers and error codes.
        for func_name in rec.names:
            entry: dict = {
                "name": func_name,
                "section": rec.section,
                "page": rec.page_name,
                "description": rec.description,
            }
            dedup_key = (func_name, rec.section)

            for code in rec.error_codes:
                ec_map[code][dedup_key] = entry

            for hdr in rec.headers:
                hdr_map[hdr][dedup_key] = entry

        # ── by_attribute ──────────────────────────────────────────────────────
        # Each row in the ATTRIBUTES table links a specific interface to a value.
        for attr_row in rec.attributes:
            func_name = _strip_iface(attr_row["interface"])
            if not func_name:
                continue
            val = attr_row["value"]
            base = _base_attr(val)

            entry = {
                "name": func_name,
                "section": rec.section,
                "page": rec.page_name,
                "description": rec.description,
            }
            dedup_key = (func_name, rec.section)

            # Index under the exact value (e.g. "MT-Safe locale").
            attr_map[val][dedup_key] = entry

            # Also index under the base token (e.g. "MT-Safe") so that a
            # bare "MT-Safe" query returns all MT-Safe variants.
            if base != val:
                attr_map[base][dedup_key] = entry

    # ── Serialise ─────────────────────────────────────────────────────────────

    def _finalise(m: dict[str, dict[tuple, dict]]) -> dict[str, list]:
        """Sort each bucket by (name, section) and convert to a plain dict."""
        return {
            k: sorted(v.values(), key=lambda e: (e["name"], e["section"]))
            for k, v in sorted(m.items())
        }

    return {
        "by_error_code": _finalise(ec_map),
        "by_header": _finalise(hdr_map),
        "by_attribute": _finalise(attr_map),
        "meta": {
            "total_pages": total,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "index_counts": {
                "error_codes": len(ec_map),
                "headers": len(hdr_map),
                "attribute_values": len(attr_map),
            },
        },
    }


# ── Persistence helpers ───────────────────────────────────────────────────────

def save_index(index: dict, path: Path, indent: int | None = None) -> None:
    """Write *index* to *path* as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=indent)
        fh.write("\n")


def load_index(path: Path) -> dict:
    """Load and return the JSON index from *path*."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Build inverted indices from Linux man pages and write index.json."
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        metavar="DIR",
        help="Root directory containing man2/ and man3/ subdirs (default: %(default)s)",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        metavar="FILE",
        help="Output JSON file (default: %(default)s)",
    )
    ap.add_argument(
        "--indent",
        type=int,
        default=None,
        metavar="N",
        help="JSON indentation (default: compact / no indentation)",
    )
    args = ap.parse_args()

    print(f"Parsing man pages from {args.data_dir} …", file=sys.stderr)
    index = build_index(iter_man_pages(args.data_dir))

    meta = index["meta"]
    print(
        f"Built index from {meta['total_pages']} pages  "
        f"({meta['index_counts']['error_codes']} error codes, "
        f"{meta['index_counts']['headers']} headers, "
        f"{meta['index_counts']['attribute_values']} attribute values)",
        file=sys.stderr,
    )

    save_index(index, args.output, indent=args.indent)
    size_kb = args.output.stat().st_size / 1024
    print(f"Saved → {args.output}  ({size_kb:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
