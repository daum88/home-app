#!/usr/bin/env python3
"""Import Coop e-receipt PDF(s) into the fridge inventory.

Usage:
    .venv/bin/python scripts/import_receipt.py /path/to/ost_nr_123.pdf
    .venv/bin/python scripts/import_receipt.py            # scan data/receipts/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.tools.receipts import import_receipt, scan_receipts_folder  # noqa: E402


async def main(paths: list[str]) -> int:
    db.init_db()
    if not paths:
        result = await scan_receipts_folder()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    failed = 0
    for path in paths:
        data = Path(path).read_bytes()
        print(f"\n=== {path} ===")
        try:
            result = await import_receipt(data)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as err:  # noqa: BLE001 — report and continue
            print(f"ERROR: {err}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Coop e-receipt PDFs.")
    parser.add_argument("paths", nargs="*", help="PDF file(s); omit to scan data/receipts/")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.paths)))
