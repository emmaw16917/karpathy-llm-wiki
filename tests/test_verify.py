import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_wiki import cleanup, cli, verify, zotero  # noqa: E402
from llm_wiki.zotero import Item  # noqa: E402

WORDS = "learned index structures improve lookup performance across many realistic workloads today "


class UrlSchemeTest(unittest.TestCase):
    def test_lost_ligatures_in_scheme_are_fixed(self):
        text = "see hps://a.org/x and htps://b.org and ttps://c.org and https://d.org http://e.org"
        fixed, count = cleanup.fix_url_schemes(text)
        self.assertEqual(fixed, "see https://a.org/x and https://b.org and https://c.org and https://d.org http://e.org")
        self.assertEqual(count, 3)


class LigatureTest(unittest.TestCase):
    PAGES = ["An efficient and different method. Staff offline first. Test the pattern, a real word: fine."]

    def test_repairs_words_only_the_pdf_can_confirm(self):
        fixed, count = cleanup.repair_ligatures("An eficient and diferent method, Eficient too.", self.PAGES)
        self.assertEqual(fixed, "An efficient and different method, Efficient too.")
        self.assertEqual(count, 3)

    def test_word_present_in_pdf_is_untouched(self):
        fixed, count = cleanup.repair_ligatures("Test the fine pattern.", self.PAGES)
        self.assertEqual((fixed, count), ("Test the fine pattern.", 0))

    def test_ambiguous_variant_is_untouched(self):
        fixed, count = cleanup.repair_ligatures("the ofer", ["offer ofter"])
        self.assertEqual((fixed, count), ("the ofer", 0))

    def test_math_and_links_are_untouched(self):
        text = "$eficient$ and ![a](p/eficient.jpg) and [x](http://e/eficient)"
        self.assertEqual(cleanup.repair_ligatures(text, self.PAGES), (text, 0))


class CoverPageTest(unittest.TestCase):
    def test_acm_cover_is_removed_through_title(self):
        body = "Latest updates: hps://x\n\nRESEARCH-ARTICLE\n\nConference Sponsors: SIGOPS\n\n# SIndex - A Key Index\n\nAuthors\n"
        result = cleanup.drop_cover(body, "SIndex: a key index")
        self.assertTrue(result.startswith("# SIndex"))
        self.assertNotIn("SIGOPS", result)

    def test_kept_without_marker_or_title(self):
        self.assertEqual(cleanup.drop_cover("Intro\n\n# T\n", "T"), "Intro\n\n# T\n")
        self.assertEqual(cleanup.drop_cover("Latest updates: x\n\nBody\n", "T"), "Latest updates: x\n\nBody\n")


class RunningLinesTest(unittest.TestCase):
    def pages(self):
        return [f"ICSE 2024, April, Lisbon\n{WORDS}{i}\nAuthorized licensed use limited\n" for i in range(5)]

    def test_detects_repeated_edge_lines_only(self):
        lines = verify.edge_lines(self.pages())
        self.assertIn("ICSE 2024, April, Lisbon", lines)
        self.assertIn("Authorized licensed use limited", lines)
        self.assertFalse(any(WORDS.strip() in line for line in lines))

    def test_short_or_numeric_edges_are_ignored(self):
        self.assertEqual(verify.edge_lines([f"12\n{WORDS}{i}\n.\n" for i in range(5)]), set())

    def test_drop_lines_removes_only_whole_matches(self):
        body = "ICSE 2024, April, Lisbon\n\nWe cite ICSE 2024, April, Lisbon here.\n"
        text, count = cleanup.drop_lines(body, {"ICSE 2024, April, Lisbon"})
        self.assertEqual(count, 1)
        self.assertIn("We cite ICSE 2024, April, Lisbon here.", text)
        self.assertFalse(text.startswith("ICSE"))


class CompareTest(unittest.TestCase):
    def test_full_coverage_has_no_flags(self):
        report = verify.compare(WORDS + "value 0.9712 and 12,345.", [WORDS + "value 0.9712 and 12345."])
        self.assertEqual((report.low_pages, report.extra_numbers, report.missing_numbers), ([], [], {}))
        self.assertEqual(report.coverage, 1.0)

    def test_dropped_page_is_flagged(self):
        other = "completely separate paragraph discussing retraining stalls concurrency buffers models errors "
        report = verify.compare(WORDS, [WORDS, other])
        self.assertEqual(report.low_pages, [2])
        self.assertLess(report.coverage, 0.7)

    def test_sparse_page_is_not_flagged(self):
        self.assertEqual(verify.compare(WORDS, [WORDS, "x y z"]).low_pages, [])

    def test_number_not_in_pdf_is_extra_and_absent_one_is_located(self):
        report = verify.compare(WORDS + "got 0.9721", [WORDS + "got 0.9712", WORDS + "plus 3.25"])
        self.assertEqual(report.extra_numbers, ["0.9721"])
        self.assertEqual(report.missing_numbers, {"1": ["0.9712"], "2": ["3.25"]})

    def test_spaced_math_numbers_match(self):
        report = verify.compare(WORDS + r"rate $0 . 0 0 1 \%$", [WORDS + "rate 0.001%"])
        self.assertEqual((report.extra_numbers, report.missing_numbers), ([], {}))

    def test_links_do_not_create_extra_numbers(self):
        report = verify.compare(WORDS + "![](a/1234567.89.jpg) [x](http://e/99.5)", [WORDS])
        self.assertEqual(report.extra_numbers, [])

    def test_ligatures_compare_equal(self):
        self.assertEqual(verify.compare("efficient offline flows " * 8, ["e\ufb03cient o\ufb00line \ufb02ows " * 8]).coverage, 1.0)


class PipelineTest(unittest.TestCase):
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

    def run_cli(self, pages):
        with mock.patch.object(cli.zotero, "find", return_value=self.item), \
                mock.patch.object(cli.zotero, "pdf_attachment", return_value=zotero.Attachment("A", self.pdf)), \
                mock.patch.object(cli.arxiv, "search", return_value=[]), \
                mock.patch.object(cli.openalex, "find_published_pdf", return_value=None), \
                mock.patch.object(cli, "_reference_pages", return_value=pages), \
                mock.patch.object(cli.mineru, "Client", return_value=self.client):
            return cli.main(["--key", "K", "--out", str(self.out), "--config", str(self.config)])

    def test_repairs_and_results_are_recorded(self):
        header = "ICSE 2024, April, Lisbon"
        self.client.parse_file.return_value = f"{header}\n\nAn eficient {WORDS} got 0.9721 at hps://a.org\n"
        pages = [f"{header}\nAn efficient {WORDS} got 0.9712 at https://a.org\n" for _ in range(3)]
        self.assertEqual(self.run_cli(pages), 0)
        text = self.out.read_text(encoding="utf-8")
        body = text.split("\n\n", 2)[2]
        self.assertIn("An efficient", body)
        self.assertIn("https://a.org", body)
        self.assertNotIn(header, body)
        self.assertIn("0.9721", body)  # numbers are reported, never rewritten
        self.assertIn("> Repairs: 1 ligature words, 1 URL schemes, 1 running lines", text)
        self.assertIn("> Verification: pdf-text-layer; word coverage 100%; low-coverage pages: none; numbers not in PDF: 1; PDF numbers not in text: 3", text)
        check = json.loads(self.out.with_name("p.check.json").read_text(encoding="utf-8"))
        self.assertEqual(check["extra_numbers"], ["0.9721"])
        self.assertEqual(check["missing_numbers"], {"1": ["0.9712"], "2": ["0.9712"], "3": ["0.9712"]})

    def test_missing_reference_is_stated(self):
        self.client.parse_file.return_value = "Body\n"
        self.assertEqual(self.run_cli(None), 0)
        self.assertIn("> Verification: skipped (no readable PDF text layer)", self.out.read_text(encoding="utf-8"))
        self.assertFalse(self.out.with_name("p.check.json").exists())


class ReadPagesTest(unittest.TestCase):
    def test_unreadable_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.pdf"
            path.write_bytes(b"not a pdf")
            self.assertIsNone(verify.read_pages(path))


if __name__ == "__main__":
    unittest.main()
