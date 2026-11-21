import unittest
from prsteward_demo.label import format_label


class LabelValueTests(unittest.TestCase):
    def test_normalized_label(self):
        self.assertEqual(format_label("  green "), "GREEN")

    def test_empty_label(self):
        self.assertEqual(format_label(" "), "")
