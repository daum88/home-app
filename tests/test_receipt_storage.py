"""Failed receipt uploads must not write outside the receipt inbox."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tools import receipts


class ReceiptStorageTests(unittest.TestCase):
    def test_untrusted_filename_stays_in_failed_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = Path(directory) / "receipts"
            with patch.object(receipts, "receipts_dir", return_value=inbox):
                receipts._save_failed(b"pdf", "../../outside.pdf")
                receipts._save_failed(b"pdf", "/tmp/absolute.pdf")
            self.assertFalse((Path(directory) / "outside.pdf").exists())
            self.assertEqual((inbox / "failed" / "outside.pdf").read_bytes(), b"pdf")
            self.assertEqual((inbox / "failed" / "absolute.pdf").read_bytes(), b"pdf")


if __name__ == "__main__":
    unittest.main()
