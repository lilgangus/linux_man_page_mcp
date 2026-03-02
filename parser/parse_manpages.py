#!/usr/bin/env python3
"""Parse Linux man pages (sections 2 & 3) into structured records.

Each ManPageRecord contains:
    filename     - source filename, e.g. "read.2.txt"
    section      - man section, e.g. "2", "3", "3type", "3const"
    page_name    - base name from filename, e.g. "read"
    names        - function/call names listed in the NAME section
    description  - one-line summary from NAME
    headers      - #include headers listed in SYNOPSIS
    error_codes  - errno values documented in the ERRORS section
    attributes   - rows from the ATTRIBUTES table: {interface, attribute, value}
    see_also     - cross-references from SEE ALSO
    synopsis     - raw text of the SYNOPSIS section
    return_value - raw text of the RETURN VALUE section

Public API:
    parse_man_page(path)          → ManPageRecord | None
    iter_man_pages(data_dir)      → Iterator[ManPageRecord]
    parse_all_man_pages(data_dir) → list[ManPageRecord]

Run as a script to emit all records as JSONL:
    python -m parser.parse_manpages [--output FILE]
"""

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "man_pages"

# ── Compiled patterns ─────────────────────────────────────────────────────────

# Section header: at column 0, uppercase letters/digits/spaces/hyphens/slashes.
# Matches: NAME, RETURN VALUE, SEE ALSO, CONFORMING TO, ERRORS, …
_RE_SECTION_HDR = re.compile(r"^[A-Z][A-Z0-9 /-]*$")

# #include directive inside SYNOPSIS.
_RE_INCLUDE = re.compile(r"^\s+#include\s+(<[^>]+>|\"[^\"]+\")")

# Error-code entry line inside ERRORS section.
# Matches 4–12 leading spaces (standard is 7) followed by one or more E-codes,
# then optional trailing text.  Does NOT match 14-space continuation lines.
_RE_ERROR_LINE = re.compile(
    r"^ {4,12}"
    r"(E[A-Z_0-9]+(?:(?:\s+or\s+|\s*,\s*)E[A-Z_0-9]+)*)"
    r"(?:\s.*)?$"
)

# Tokenise individual error codes from a matched group.
_RE_ECODE_TOKEN = re.compile(r"E[A-Z_0-9]+")

# Function reference: name(section), e.g. read(2), pthread_create(3).
_RE_FUNC_REF = re.compile(r"\b(\w+)\((\d[a-z]*)\)")


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ManPageRecord:
    filename: str
    section: str
    page_name: str
    names: list[str] = field(default_factory=list)
    description: str = ""
    headers: list[str] = field(default_factory=list)
    error_codes: list[str] = field(default_factory=list)
    attributes: list[dict] = field(default_factory=list)
    see_also: list[str] = field(default_factory=list)
    synopsis: str = ""
    return_value: str = ""

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict of this record."""
        return asdict(self)


# ── Section splitting ─────────────────────────────────────────────────────────

def _split_sections(text: str) -> dict[str, str]:
    """Split man page text into {SECTION_NAME: content_text} dict.

    Section headers are lines at column 0 that match _RE_SECTION_HDR.
    The first line (page header) and last line (footer) do not match because
    they contain lowercase letters and/or parentheses.
    """
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in text.splitlines():
        # Column-0, all-caps line → new section
        if line and not line[0].isspace() and _RE_SECTION_HDR.match(line.rstrip()):
            current = line.rstrip()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)

    return {k: "\n".join(v) for k, v in sections.items()}


# ── Section-specific field parsers ────────────────────────────────────────────

def _parse_name(text: str) -> tuple[list[str], str]:
    """Parse NAME section text → (names_list, description).

    Example input: "       accept, accept4 - accept a connection on a socket"
    Returns: (["accept", "accept4"], "accept a connection on a socket")
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return [], ""
    full = " ".join(lines)
    if " - " in full:
        names_part, desc = full.split(" - ", 1)
    else:
        names_part, desc = full, ""
    names = [n.strip() for n in re.split(r"[,\s]+", names_part) if n.strip()]
    return names, desc.strip()


def _parse_synopsis(text: str) -> tuple[list[str], str]:
    """Parse SYNOPSIS section text → (include_headers, raw_text).

    Returns all #include lines as a list of header strings (e.g. "<unistd.h>")
    and the full raw synopsis text for signature inspection.
    """
    seen: set[str] = set()
    headers: list[str] = []
    for line in text.splitlines():
        m = _RE_INCLUDE.match(line)
        if m:
            hdr = m.group(1)
            if hdr not in seen:
                seen.add(hdr)
                headers.append(hdr)
    return headers, text.strip()


def _parse_errors(text: str) -> list[str]:
    """Parse ERRORS section text → sorted, deduplicated list of errno names.

    Handles all common formats:
      EAGAIN <description>
      EAGAIN or EWOULDBLOCK
      ENOBUFS, ENOMEM
      EINVAL (accept4()) <description>
    """
    codes: set[str] = set()
    for line in text.splitlines():
        m = _RE_ERROR_LINE.match(line)
        if m:
            for token in _RE_ECODE_TOKEN.findall(m.group(1)):
                codes.add(token)
    return sorted(codes)


def _parse_attributes(text: str) -> list[dict]:
    """Parse ATTRIBUTES table → list of {interface, attribute, value} dicts.

    Handles:
    - Multiple data rows (separated by ├...┤ lines)
    - Multiple function names per row (comma-separated in the interface column)
    - Interface names that span two table rows (continuation rows where the
      Attribute and Value columns are blank)

    Example output:
        [{"interface": "read", "attribute": "Thread safety", "value": "MT-Safe"}]
    """
    results: list[dict] = []
    current_ifaces: list[str] = []
    current_attr = ""
    current_val = ""
    in_data = False

    def _flush() -> None:
        nonlocal current_ifaces, current_attr, current_val
        if current_ifaces and current_attr:
            for iface in current_ifaces:
                if iface:
                    results.append({
                        "interface": iface,
                        "attribute": current_attr,
                        "value": current_val,
                    })
        current_ifaces = []
        current_attr = ""
        current_val = ""

    for line in text.splitlines():
        s = line.strip()

        # ├ separates the header row from data rows, or consecutive data rows.
        # ┌ is the top border of the table.
        if "├" in s or "┌" in s:
            if in_data:
                _flush()
            in_data = "├" in s  # only enter data mode after ├
            continue

        # └ is the bottom border — end of table.
        if "└" in s:
            _flush()
            in_data = False
            continue

        if in_data and "│" in s:
            # Split by the vertical-bar box character; columns are at [1],[2],[3].
            parts = [p.strip() for p in s.split("│")]
            if len(parts) >= 4:
                iface_col = parts[1]
                attr_col = parts[2]
                val_col = parts[3]

                if attr_col:
                    # New entry row: attribute column is populated.
                    _flush()
                    current_ifaces = [i.strip() for i in iface_col.split(",") if i.strip()]
                    current_attr = attr_col
                    current_val = val_col
                else:
                    # Continuation row: attribute/value columns are blank.
                    current_ifaces += [i.strip() for i in iface_col.split(",") if i.strip()]

    return results


def _parse_see_also(text: str) -> list[str]:
    """Parse SEE ALSO section text → sorted list of "name(section)" strings.

    Only considers indented lines to avoid picking up the page footer line
    (which is at column 0 and also contains a "name(section)" token).
    """
    refs: set[str] = set()
    for line in text.splitlines():
        if line and line[0].isspace():
            for m in _RE_FUNC_REF.finditer(line):
                refs.add(f"{m.group(1)}({m.group(2)})")
    return sorted(refs)


# ── Filename helpers ──────────────────────────────────────────────────────────

def _filename_to_name_section(filename: str) -> tuple[str, str]:
    """Extract (page_name, section) from filenames like 'read.2.txt'.

    Examples:
        'read.2.txt'           → ('read', '2')
        'pthread_create.3.txt' → ('pthread_create', '3')
        'EOF.3const.txt'       → ('EOF', '3const')
        '_Exit.2.txt'          → ('_Exit', '2')
    """
    stem = filename[:-4] if filename.endswith(".txt") else filename
    idx = stem.rfind(".")
    if idx >= 0:
        return stem[:idx], stem[idx + 1:]
    return stem, ""


# ── Top-level parsers ─────────────────────────────────────────────────────────

def parse_man_page(path: Path) -> "ManPageRecord | None":
    """Parse a single man page text file into a ManPageRecord.

    Returns None if the file cannot be read or is empty.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if not text.strip():
        return None

    page_name, section = _filename_to_name_section(path.name)
    secs = _split_sections(text)

    names, description = _parse_name(secs.get("NAME", ""))

    headers, synopsis = _parse_synopsis(secs.get("SYNOPSIS", ""))

    error_codes = _parse_errors(secs.get("ERRORS", ""))

    attributes = _parse_attributes(secs.get("ATTRIBUTES", ""))

    see_also = _parse_see_also(secs.get("SEE ALSO", ""))

    return_value = secs.get("RETURN VALUE", secs.get("RETURN VALUES", "")).strip()

    return ManPageRecord(
        filename=path.name,
        section=section,
        page_name=page_name,
        names=names,
        description=description,
        headers=headers,
        error_codes=error_codes,
        attributes=attributes,
        see_also=see_also,
        synopsis=synopsis,
        return_value=return_value,
    )


def iter_man_pages(data_dir: Path = DATA_DIR) -> Iterator[ManPageRecord]:
    """Yield ManPageRecord for every man page .txt file under *data_dir*.

    Traverses man2/ and man3/ subdirectories in sorted order.
    """
    for section_dir in sorted(data_dir.iterdir()):
        if not section_dir.is_dir():
            continue
        for txt_file in sorted(section_dir.glob("*.txt")):
            record = parse_man_page(txt_file)
            if record is not None:
                yield record


def parse_all_man_pages(data_dir: Path = DATA_DIR) -> list[ManPageRecord]:
    """Parse all man pages under *data_dir* and return them as a list."""
    return list(iter_man_pages(data_dir))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    """Write all parsed records as JSONL to stdout or a file."""
    import argparse

    ap = argparse.ArgumentParser(
        description="Parse Linux man pages into structured JSONL."
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
        default=None,
        metavar="FILE",
        help="Write JSONL output to FILE instead of stdout",
    )
    ap.add_argument(
        "--stats",
        action="store_true",
        help="Print per-field coverage statistics to stderr after parsing",
    )
    args = ap.parse_args()

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout

    counts: dict[str, int] = {
        "total": 0,
        "has_names": 0,
        "has_headers": 0,
        "has_errors": 0,
        "has_attributes": 0,
        "has_see_also": 0,
    }

    try:
        for record in iter_man_pages(args.data_dir):
            out.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            counts["total"] += 1
            if record.names:
                counts["has_names"] += 1
            if record.headers:
                counts["has_headers"] += 1
            if record.error_codes:
                counts["has_errors"] += 1
            if record.attributes:
                counts["has_attributes"] += 1
            if record.see_also:
                counts["has_see_also"] += 1
    finally:
        if args.output:
            out.close()

    n = counts["total"]
    print(f"Parsed {n} man pages.", file=sys.stderr)
    if args.stats and n:
        for key, val in counts.items():
            if key == "total":
                continue
            print(f"  {key:<20s} {val:5d} / {n}  ({100*val/n:.1f}%)", file=sys.stderr)


if __name__ == "__main__":
    main()
