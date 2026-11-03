import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_wiki import cli, quality, zotero  # noqa: E402
from llm_wiki.zotero import Item  # noqa: E402

PROSE = ("Indexes can improve query-processing performance by avoiding full table scans in most workloads. "
         "Learned models replace comparison search with a prediction followed by a bounded local correction step. "
         "We evaluate eleven structures across read-heavy, write-heavy, and mixed scenarios with several datasets. ") * 1
OTHER = ("Throughput drops when the error bound grows because the last-mile search must scan a wider range of keys. "
         "Concurrency control adds further overhead, and retraining stalls writers while new models are being built. ")
DOUBLED = ("Indexes can improve query-processing performance by avoidingIndexes can improve query-processing "
           "performance by avoiding full table scans. Although traditional indexes have full table scans. "
           "Although traditional indexes have been widely used, learned indexes are proposed to adopt machine"
           "been widely used, learned indexes are proposed to adopt machine learning models instead of trees.")


class DoubledTextTest(unittest.TestCase):
    def test_clean_prose_scores_low(self):
        self.assertLess(quality.doubled_ratio(PROSE + "\n\n" + OTHER), quality.DOUBLED_LIMIT)

    def test_overlaid_text_scores_high(self):
        self.assertGreater(quality.doubled_ratio(DOUBLED), quality.DOUBLED_LIMIT)

    def test_partly_doubled_document_is_caught(self):
        # A real overlaid PDF scored 0.181 while clean papers scored at most 0.006.
        clean = "\n\n".join(f"Section {i}. {OTHER if i % 2 else PROSE}" for i in range(4))
        mixed = clean + "\n\n" + DOUBLED
        self.assertGreater(quality.doubled_ratio(mixed), quality.DOUBLED_LIMIT)

    def test_tables_and_equations_are_ignored(self):
        row = "<table>" + "<tr><td>Time (s)</td><td>2.258</td><td>2.258</td></tr>" * 30 + "</table>"
        equation = "$$\n" + "x_{1}+x_{2}+x_{3}+" * 30 + "\n$$"
        self.assertEqual(quality.doubled_ratio(row + "\n\n" + equation), 0)


class StripTitleTest(unittest.TestCase):
    def test_title_after_front_matter_is_removed(self):
        body = "Sponsors: SIGOPS\n\n# SIndex: A Key Index\n\nAuthor\n\n# Other\n"
        result = cli._strip_title(body, "SIndex - a key index")
        self.assertNotIn("# SIndex", result)
        self.assertIn("Sponsors: SIGOPS", result)
        self.assertIn("# Other", result)

    def test_unrelated_first_heading_is_kept(self):
        self.assertIn("# Intro", cli._strip_title("# Intro\n\nText\n", "Some Title"))


class GateRouteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.out = root / "raw" / "p.md"
        self.pdf = root / "local.pdf"
        self.pdf.write_bytes(b"%PDF clean")
        self.config = root / "c.json"
        self.config.write_text('{"mineru": {"api_token": "T"}, "zotero": {"data_dir": "D:/Z"}}', encoding="utf-8")
        self.client = mock.MagicMock()
        self.item = Item("K", "conferencePaper", "Title", "10.1/x", "", "", "", "2020", "Sun")

    def run_cli(self, *extra):
        with mock.patch.object(cli, "_reference_pages", return_value=None), \
                mock.patch.object(cli.zotero, "find", return_value=self.item), \
                mock.patch.object(cli.zotero, "pdf_attachment", return_value=zotero.Attachment("A", self.pdf)), \
                mock.patch.object(cli.arxiv, "search", return_value=[]), \
                mock.patch.object(cli.openalex, "find_published_pdf", return_value=None), \
                mock.patch.object(cli.mineru, "Client", return_value=self.client):
            return cli.main(["--key", "K", "--out", str(self.out), "--config", str(self.config), *extra])

    def test_doubled_upload_is_not_written(self):
        self.client.parse_file.return_value = DOUBLED
        self.assertEqual(self.run_cli(), 3)
        self.assertFalse(self.out.exists())

    def test_pdf_url_is_tried_first_and_recorded(self):
        self.client.parse_url.return_value = PROSE
        self.assertEqual(self.run_cli("--pdf-url", "https://pub/clean.pdf"), 0)
        self.client.parse_file.assert_not_called()
        self.assertIn("> Source: https://pub/clean.pdf", self.out.read_text(encoding="utf-8"))

    def test_doubled_url_falls_through_to_upload(self):
        self.client.parse_url.return_value = DOUBLED
        self.client.parse_file.return_value = PROSE
        self.assertEqual(self.run_cli("--pdf-url", "https://pub/bad.pdf"), 0)
        self.client.parse_file.assert_called_once()


if __name__ == "__main__":
    unittest.main()
