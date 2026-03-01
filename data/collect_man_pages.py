#!/usr/bin/env python3
"""Collect Linux man pages (sections 2 & 3) as plain text files.

Output: data/man_pages/man2/ and data/man_pages/man3/

Usage:
  python3 data/collect_man_pages.py, ensure that the man pages package exists
"""

import os
import re
import subprocess
from pathlib import Path

SECTIONS = ("2", "3")
OUTPUT_BASE = Path(__file__).resolve().parent / "man_pages"


def get_man_dirs() -> list[Path]:
    raw = subprocess.check_output(["manpath"], text=True).strip()
    return [Path(p) for p in raw.split(":") if Path(p).is_dir()]


def find_pages(section: str, man_dirs: list[Path]) -> dict[str, Path]:
    """Return {page_stem: source_path} for the given section, deduplicated.

    stem includes the full sub-section suffix, e.g. 'read.2', 'size_t.3type'.
    Handles .gz, .bz2, .xz, and .zst compression.
    """
    pattern = re.compile(rf"^(.+)\.({section}\w*)(\.(gz|bz2|xz|zst))?$")
    seen: dict[str, Path] = {}
    for base in man_dirs:
        d = base / f"man{section}"
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            m = pattern.match(f.name)
            if m:
                stem = f"{m.group(1)}.{m.group(2)}"
                if stem not in seen:
                    seen[stem] = f
    return seen


def render(source: Path) -> str | None:
    """Render a man page to plain text by passing the source path directly to man.

    Using the file path (not name + section) ensures we render exactly the file
    found by find_pages, avoiding any re-resolution ambiguity for sub-sections
    like .3type or .3const. man-db still runs soelim on the file, so .so stubs
    are followed correctly.
    """
    man = col = None
    try:
        man = subprocess.Popen(
            ["man", "-P", "cat", str(source)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "MANWIDTH": "120"},
        )
        col = subprocess.Popen(
            ["col", "-bx"],
            stdin=man.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        man.stdout.close()
        out, _ = col.communicate(timeout=20)
        man.wait(timeout=5)
        text = out.decode("utf-8", errors="replace")
        return text if text.strip() else None
    except Exception:
        return None
    finally:
        for proc in (col, man):
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()


def main() -> None:
    man_dirs = get_man_dirs()
    print(f"Man path: {':'.join(str(p) for p in man_dirs)}\n")

    total_ok = total_fail = total_skip = 0

    for section in SECTIONS:
        pages = find_pages(section, man_dirs)
        out_dir = OUTPUT_BASE / f"man{section}"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"Section {section}: {len(pages)} pages → {out_dir}")

        for i, (stem, src) in enumerate(sorted(pages.items()), 1):
            out_file = out_dir / f"{stem}.txt"
            if out_file.exists():
                print(f"  [{i:4d}/{len(pages)}] SKIP {stem}", flush=True)
                total_skip += 1
                continue
            text = render(src)
            if text:
                out_file.write_text(text, encoding="utf-8")
                print(f"  [{i:4d}/{len(pages)}] OK   {stem}", flush=True)
                total_ok += 1
            else:
                print(f"  [{i:4d}/{len(pages)}] FAIL {stem}", flush=True)
                total_fail += 1

        print()

    print(f"Done. {total_ok} OK, {total_fail} failed, {total_skip} skipped.")


if __name__ == "__main__":
    main()
