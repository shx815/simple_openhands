import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from prsteward_demo.label import format_label


class QuietOutputProbe(unittest.TestCase):
    def test_json_callers_own_stdout_and_stderr(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            format_label("green")
        self.assertEqual(stdout.getvalue(), "", "format_label wrote to the caller's stdout")
        self.assertEqual(stderr.getvalue(), "", "format_label wrote to the caller's stderr")
