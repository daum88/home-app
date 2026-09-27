"""Shared formatting used by search and Transmission tools."""
import unittest

from app.tools.base import format_size


class FormatSizeTests(unittest.TestCase):
    def test_sizes(self):
        for size, label in (
            (0, "0 B"),
            (512, "512 B"),
            (1024, "1.0 KB"),
            (1024**2, "1.0 MB"),
            (1024**3, "1.0 GB"),
            (1024**4, "1.0 TB"),
        ):
            with self.subTest(size=size):
                self.assertEqual(format_size(size), label)


if __name__ == "__main__":
    unittest.main()
