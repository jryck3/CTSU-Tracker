#!/usr/bin/env python3
"""Print text from the current protocol PDF for reading. Nothing is saved.

    protocol_text.py S1931 --find "ELIGIBILITY CRITERIA|SCHEMA"   # page numbers that match
    protocol_text.py S1931 --pages 5-9                            # text of pages 5 to 9 (1-based)
    protocol_text.py S1931 --layout --pages 6                     # keep the column layout
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protocol_library as lib  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("protocol")
    parser.add_argument("--pages", help="1-based page or range, for example 7 or 7-12")
    parser.add_argument("--find", help="Regex; prints matching page numbers and the matching lines")
    parser.add_argument("--layout", action="store_true", help="Layout-preserving extraction")
    args = parser.parse_args()
    from pypdf import PdfReader
    path = lib.current_pdf(args.protocol)
    if path is None:
        raise SystemExit("No protocol on file for %s." % args.protocol)
    reader = PdfReader(str(path))
    entry = lib.manifest().get(args.protocol) or {}
    print("# %s | %s | %s pages | version %s" % (args.protocol, path.name, len(reader.pages), entry.get("version")))
    mode = {"extraction_mode": "layout"} if args.layout else {}
    if args.find:
        pattern = re.compile(args.find, re.I)
        for index, page in enumerate(reader.pages):
            text = page.extract_text(**mode) or ""
            hits = [line.strip() for line in text.splitlines() if pattern.search(line)]
            if hits:
                print("p%d: %s" % (index + 1, " | ".join(hit[:120] for hit in hits[:4])))
        return
    first, last = 1, min(len(reader.pages), 3)
    if args.pages:
        parts = args.pages.split("-")
        first = int(parts[0])
        last = int(parts[-1])
    for number in range(first, min(last, len(reader.pages)) + 1):
        print("\n=== page %d ===" % number)
        print(reader.pages[number - 1].extract_text(**mode) or "")


if __name__ == "__main__":
    main()
