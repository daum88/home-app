"""Deployment smoke checks only query health and read-only status tools."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from scripts import device_check


class DeviceCheckTests(unittest.TestCase):
    def test_inventory_consistency_and_read_only_status(self):
        called = []

        def respond(request):
            called.append(request.url.path)
            if request.url.path == "/api/health":
                return httpx.Response(200, json={"ok": True})
            name = request.url.path.rsplit("/", 1)[-1]
            data = {
                "fridge_inventory_list": {"items": [{"id": 10, "name": "Milk"}]},
                "inventory_expiring": {"items": [{"id": 10, "name": "Milk"}]},
                "washer_status": {}, "fridge_status": {}, "ventilation_status": {},
            }[name]
            return httpx.Response(200, json={"ok": True, "data": data})

        client = httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test")
        with patch.object(device_check.httpx, "Client", return_value=client):
            self.assertEqual(device_check.check("http://test", include_devices=True), 0)
        self.assertEqual(called, [
            "/api/health", "/api/tools/fridge_inventory_list",
            "/api/tools/inventory_expiring", "/api/tools/washer_status",
            "/api/tools/fridge_status", "/api/tools/ventilation_status",
        ])

    def test_mismatched_expiry_ids_fail(self):
        def respond(request):
            if request.url.path == "/api/health":
                return httpx.Response(200, json={"ok": True})
            items = [{"id": 1}] if request.url.path.endswith("fridge_inventory_list") else [{"id": 2}]
            return httpx.Response(200, json={"ok": True, "data": {"items": items}})

        client = httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test")
        with patch.object(device_check.httpx, "Client", return_value=client):
            self.assertEqual(device_check.check("http://test", include_devices=False), 1)


if __name__ == "__main__":
    unittest.main()
