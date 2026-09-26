#!/usr/bin/env python3
"""CLI smoke test for each tool — no LLM required.

Prints the sanitized result of every configured tool and exits non-zero if any
tool fails. Run it on the Pi BEFORE wiring anything to the LLM:

    .venv/bin/python scripts/test_tools.py                # all tools
    .venv/bin/python scripts/test_tools.py --tool washer_status
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app import db  # noqa: E402
from app.tools import TOOLS, run_tool  # noqa: E402

# Tool name → argument defaults for a smoke test.
SMOKE_ARGS: dict[str, dict] = {
    "list_torrents": {},
    "washer_status": {},
    "fridge_status": {},
    "ventilation_status": {},
    "inventory_list": {},
    "inventory_expiring": {"days": 3},
}

# Which env vars gate each tool (for a friendly "not configured" hint).
GATES: dict[str, str] = {
    "list_torrents": "TRANSMISSION_URL",
    "washer_status": "SMARTTHINGS_PAT",
    "fridge_status": "HON_USER",
    "ventilation_status": "SAVECONNECT_URL",
    "search_torrents": "PROWLARR_API_KEY",
    "inventory_list": "DB_PATH",
}


async def main(tool_name: str | None) -> int:
    db.init_db()
    names = [tool_name] if tool_name else list(SMOKE_ARGS.keys())
    failed = 0

    for name in names:
        print(f"\n=== {name} ===")
        gate = GATES.get(name)
        if gate and not getattr(config, gate, ""):
            print("  SKIP — not configured (set %s in .env)" % gate)
            continue
        result = await run_tool(name, SMOKE_ARGS.get(name, {}))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("ok") is False:
            failed += 1

    print(f"\n{len(names)} tool(s) checked, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smoke-test one or all tools.")
    parser.add_argument("--tool", help="run a single tool by name")
    parser.add_argument("--list", action="store_true", help="list all registered tools")
    args = parser.parse_args()

    if args.list:
        for name in TOOLS:
            print(f"{name:22s} {TOOLS[name]['description']}")
        sys.exit(0)

    sys.exit(asyncio.run(main(args.tool)))
