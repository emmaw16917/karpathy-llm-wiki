"""Regressions for non-UTF-8 consoles (Chinese Windows defaults to GBK)."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_evidence.py"


class NonUtf8ConsoleTest(unittest.TestCase):
    def test_gbk_stdout_survives_unencodable_suspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw").mkdir()
            (root / "wiki").mkdir()
            (root / "raw" / "a.md").write_text("# A\n\nnothing here\n", encoding="utf-8")
            (root / "wiki" / "a.md").write_text(
                '# A\n\n> Raw: [a](../raw/a.md)\n\nHe said "values x⋯y are not in the raw file".\n',
                encoding="utf-8",
            )
            env = {**os.environ, "PYTHONIOENCODING": "gbk"}
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)], capture_output=True, env=env
            )
        self.assertEqual(result.returncode, 0, result.stderr.decode("gbk", "replace"))
        self.assertIn(b"1 fidelity suspect", result.stdout)
        self.assertIn(b"\\u22ef", result.stdout)


if __name__ == "__main__":
    unittest.main()
