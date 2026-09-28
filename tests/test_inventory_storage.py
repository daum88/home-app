"""Regression tests for barcode and barcode-less inventory persistence."""
from __future__ import annotations

import sqlite3
import unittest

from app import db
from tests.base import HomeTestCase


class InventoryStorageTests(HomeTestCase):
    def setUp(self):
        super().setUp()
        self.path = self.use_temp_db()

    def test_missing_barcodes_do_not_overwrite_other_receipt_items(self):
        db.inventory_add(name="Milk", barcode="")
        db.inventory_add(name="Bread", barcode="")
        items = db.inventory_list()
        self.assertEqual({item["name"] for item in items}, {"Milk", "Bread"})
        self.assertTrue(all(item["barcode"] is None for item in items))

    def test_identical_barcodes_are_distinct_packages(self):
        first = db.inventory_add(name="Milk", barcode="12345678", expires_on="2026-09-29")
        second = db.inventory_add(name="Milk", barcode="12345678", expires_on="2026-10-05")
        items = db.inventory_list()
        self.assertNotEqual(first, second)
        self.assertEqual(len(items), 2)
        self.assertEqual({item["expires_on"] for item in items}, {"2026-09-29", "2026-10-05"})

    def test_receipt_line_is_idempotent_and_item_removal_is_local(self):
        first = db.inventory_add(name="Bread", receipt_no="receipt-1", receipt_line=0)
        repeated = db.inventory_add(name="Bread", receipt_no="receipt-1", receipt_line=0)
        self.assertEqual(first, repeated)
        self.assertEqual(len(db.inventory_list()), 1)
        self.assertTrue(db.inventory_remove(first))
        self.assertFalse(db.inventory_remove(first))
        self.assertEqual(db.inventory_list(), [])

    def test_existing_empty_barcode_is_migrated(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO inventory (barcode, name) VALUES ('', 'Old item')")
        db.init_db()
        db.init_db()
        db.inventory_add(name="New item", barcode="")
        items = db.inventory_list()
        self.assertEqual({item["name"] for item in items}, {"Old item", "New item"})
        self.assertTrue(all(item["barcode"] is None for item in items))
        self.assertEqual(len([item for item in items if item["name"] == "Old item"]), 1)
        old_id = next(item["id"] for item in items if item["name"] == "Old item")
        self.assertTrue(db.inventory_remove(old_id))
        db.init_db()
        self.assertNotIn("Old item", [item["name"] for item in db.inventory_list()])


if __name__ == "__main__":
    unittest.main()
