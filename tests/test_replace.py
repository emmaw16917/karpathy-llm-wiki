import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_wiki import cli, mineru, zotero  # noqa: E402
from llm_wiki.zotero import Item  # noqa: E402


class ReplaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.out = root / "raw" / "t" / "p.md"
        self.assets = root / "raw" / "assets" / "p"
        self.pdf = root / "local.pdf"
        self.pdf.write_bytes(b"%PDF clean")
        self.config = root / "c.json"
        self.config.write_text('{"mineru": {"api_token": "T"}, "zotero": {"data_dir": "D:/Z"}}', encoding="utf-8")
        self.client = mock.MagicMock()
        self.client.parse_file.side_effect = self.parse
        self.item = Item("K", "conferencePaper", "Title", "10.1/x", "", "", "", "2020", "Sun")

    def parse(self, _path, assets):
        assets.mkdir(parents=True)
        (assets / "new.jpg").write_bytes(b"N")
        return "New body ![](images/new.jpg)\n"

    def run_cli(self, *extra):
        with mock.patch.object(cli, "_reference_pages", return_value=None), \
                mock.patch.object(cli.zotero, "find", return_value=self.item), \
                mock.patch.object(cli.zotero, "pdf_attachment", return_value=zotero.Attachment("A", self.pdf)), \
                mock.patch.object(cli.arxiv, "search", return_value=[]), \
                mock.patch.object(cli.openalex, "find_published_pdf", return_value=None), \
                mock.patch.object(cli.mineru, "Client", return_value=self.client):
            return cli.main(["--key", "K", "--out", str(self.out), "--config", str(self.config), *extra])

    def old_version(self):
        self.out.parent.mkdir(parents=True)
        self.out.write_bytes(b"old body\n")
        self.assets.mkdir(parents=True)
        (self.assets / "old.jpg").write_bytes(b"O")
        return hashlib.sha256(b"old body\n").hexdigest()

    def test_replace_swaps_files_and_records_old_hash(self):
        digest = self.old_version()
        self.assertEqual(self.run_cli("--replace", "--reason", "bad table"), 0)
        text = self.out.read_text(encoding="utf-8")
        self.assertIn("New body ![](../assets/p/new.jpg)", text)
        self.assertIn(f"> Replaces: sha256:{digest} (bad table)", text)
        self.assertEqual([p.name for p in self.assets.iterdir()], ["new.jpg"])
        self.assertEqual(sorted(p.name for p in self.out.parent.iterdir()), ["p.md"])
        self.assertEqual(sorted(p.name for p in self.assets.parent.iterdir()), ["p"])

    def test_failed_extraction_leaves_old_version_intact(self):
        self.old_version()
        self.client.parse_file.side_effect = mineru.MineruError("down")
        self.assertEqual(self.run_cli("--replace", "--reason", "x"), 3)
        self.assertEqual(self.out.read_bytes(), b"old body\n")
        self.assertEqual([p.name for p in self.assets.iterdir()], ["old.jpg"])
        self.assertEqual(sorted(p.name for p in self.assets.parent.iterdir()), ["p"])

    def test_replace_requires_a_reason(self):
        self.old_version()
        self.assertEqual(self.run_cli("--replace"), 2)
        self.assertEqual(self.out.read_bytes(), b"old body\n")

    def test_replace_requires_an_existing_file(self):
        self.assertEqual(self.run_cli("--replace", "--reason", "x"), 2)
        self.assertFalse(self.out.exists())

    def test_default_still_refuses_to_overwrite(self):
        self.old_version()
        self.assertEqual(self.run_cli(), 2)
        self.assertEqual(self.out.read_bytes(), b"old body\n")


if __name__ == "__main__":
    unittest.main()
