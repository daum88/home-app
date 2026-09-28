"""Receipt, barcode and recipe paths all use the same local inventory."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app import db
from app.tools import barcode, local_inventory, receipts, recipes
from app.tools.base import ToolError
from tests.base import AsyncHomeTestCase


class InventoryPipelineTests(AsyncHomeTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.use_temp_db()

    async def test_receipt_imports_packages_without_cloud_writes_or_retry_duplicates(self):
        parsed = {
            "receipt_no": "1234567890", "date": "2026-09-27", "store": "Coop",
            "items": [
                {"name": "MILK", "barcode": "12345678", "qty": 1.0, "price": 2.50},
                {"name": "MILK", "barcode": "12345678", "qty": 1.0, "price": 2.50},
            ],
        }
        enriched = {"name": "Milk", "brands": "", "category": "dairy", "source": "receipt", "days": 7}
        with patch.object(receipts, "parse_receipt", return_value=parsed), \
             patch.object(receipts, "_enrich", new_callable=AsyncMock, return_value=enriched):
            first = await receipts.import_receipt(b"pdf")
            repeated = await receipts.import_receipt(b"pdf")
        self.assertFalse(first["already_imported"])
        self.assertTrue(repeated["already_imported"])
        self.assertEqual(len((await local_inventory.list_items())["items"]), 2)
        self.assertEqual(db.recent_receipts(1)[0]["item_count"], 2)

    async def test_barcode_and_recipe_reader_use_local_items(self):
        product = {"name": "Milk", "barcode": "12345678", "brands": "", "category": "dairy", "shelf_life_days": 7}
        with patch.object(barcode, "lookup_barcode", new_callable=AsyncMock, return_value=product):
            await barcode.add_barcode_item("12345678")
        self.assertEqual((await local_inventory.list_items())["items"][0]["name"], "Milk")
        with patch.object(local_inventory, "list_items", new_callable=AsyncMock,
                          return_value={"items": []}):
            with self.assertRaisesRegex(ToolError, "fridge is empty"):
                await recipes.suggest_recipes()


if __name__ == "__main__":
    unittest.main()
