"""Canonical local inventory remains usable offline and imports hOn non-destructively."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app import config, db
from app.tools import hon_inventory, inventory, local_inventory
from app.tools.base import ToolError


class LocalInventoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path_patch = patch.object(config, "DB_PATH", str(Path(self.temp.name) / "home.db"))
        path_patch.start()
        self.addCleanup(path_patch.stop)
        db.init_db()

    async def test_add_expiring_and_remove_work_without_hon(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        with patch.object(config, "HON_USER", ""), patch.object(config, "HON_PASS", ""):
            first = await local_inventory.add_item("Milk", expires_on=tomorrow)
            second = await local_inventory.add_item("Milk", expires_on=tomorrow)
            self.assertNotEqual(first["item_id"], second["item_id"])
            listed = await local_inventory.list_items()
            expiring = await inventory.inventory_expiring(7)
            self.assertEqual(len(listed["items"]), 2)
            self.assertEqual({it["id"] for it in expiring["items"]},
                             {first["item_id"], second["item_id"]})
            self.assertEqual((await local_inventory.remove_item(first["item_id"]))["removed"], True)
            self.assertEqual(len((await local_inventory.list_items())["items"]), 1)
            with self.assertRaises(ToolError):
                await local_inventory.import_hon()

    async def test_hon_import_is_idempotent_and_does_not_restore_removed_items(self):
        snapshot = {"items": [
            {"id": 100, "name": "Milk", "quantity": 1, "unit": "pz", "position": "fridge", "expires_on": "2026/10/12"},
            {"id": 101, "name": "Eggs", "quantity": 2, "unit": "pz", "position": "fridge", "expires_on": ""},
        ]}
        with patch.object(config, "HON_USER", "user"), patch.object(config, "HON_PASS", "pass"), \
             patch.object(hon_inventory, "list_items", new_callable=AsyncMock, return_value=snapshot):
            self.assertEqual((await local_inventory.import_hon())["imported"], 2)
            self.assertEqual((await local_inventory.import_hon())["imported"], 0)
            items = (await local_inventory.list_items())["items"]
            self.assertEqual(len(items), 2)
            self.assertEqual(next(it for it in items if it["name"] == "Milk")["expires_on"], "2026-10-12")
            await local_inventory.remove_item(items[0]["id"])
            self.assertEqual((await local_inventory.import_hon())["imported"], 0)
            self.assertEqual(len((await local_inventory.list_items())["items"]), 1)

    async def test_failed_cloud_fetch_leaves_local_items_intact(self):
        local = await local_inventory.add_item("Bread")
        with patch.object(config, "HON_USER", "user"), patch.object(config, "HON_PASS", "pass"), \
             patch.object(hon_inventory, "list_items", new_callable=AsyncMock, side_effect=ToolError("offline")):
            with self.assertRaisesRegex(ToolError, "offline"):
                await local_inventory.import_hon()
        self.assertEqual((await local_inventory.list_items())["items"][0]["id"], local["item_id"])


if __name__ == "__main__":
    unittest.main()
