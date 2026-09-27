#!/usr/bin/env python3
"""Read-only API acceptance checks for a deployed Pi; never controls devices."""
from __future__ import annotations

import argparse
import sys

import httpx


def check(base: str, include_devices: bool) -> int:
    with httpx.Client(base_url=base, timeout=15) as client:
        try:
            health = client.get("/api/health")
            health.raise_for_status()
            if health.json().get("ok") is not True:
                raise ValueError("health check failed")

            def tool(name: str, args: dict | None = None) -> dict:
                response = client.post(f"/api/tools/{name}", json={"args": args or {}})
                response.raise_for_status()
                result = response.json()
                if not result.get("ok"):
                    raise ValueError(f"{name}: {result.get('error')}")
                return result["data"]

            local = tool("fridge_inventory_list")["items"]
            expiring = tool("inventory_expiring", {"days": 7})["items"]
            local_ids = {item["id"] for item in local}
            if not all(item["id"] in local_ids for item in expiring):
                raise ValueError("widget expiry data disagrees with the fridge list")
            print(f"PASS: API healthy; {len(local)} fridge items; {len(expiring)} expiring items")
            if include_devices:
                for name in ("washer_status", "fridge_status", "ventilation_status"):
                    try:
                        tool(name)
                        print(f"PASS: {name}")
                    except (httpx.HTTPError, ValueError) as err:
                        print(f"WARN: {name}: {err}")
            return 0
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as err:
            print(f"FAIL: {err}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="Pi API address")
    parser.add_argument("--devices", action="store_true", help="also read device status")
    args = parser.parse_args()
    sys.exit(check(args.base, args.devices))
