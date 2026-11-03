import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_wiki import cli, tables  # noqa: E402

HTML_BODY = """Intro.

![TABLE I: Summary of Log Datasets](https://arxiv.org/html/1v1/datasets.svg)

Middle.

![TABLE II: Compression Results](https://arxiv.org/html/1v1/results.svg)

![Fig. 1: Flow](https://arxiv.org/html/1v1/flow.png)
"""
MINERU_BODY = """Intro.

TABLE I SUMMARY OF LOG DATASETS

<table><tr><td>HDFS</td><td>1.58</td></tr></table>

Text.

TABLE III OTHER

<table><tr><td>Other</td></tr></table>
"""


class MergeTablesTest(unittest.TestCase):
    def test_matching_table_is_inserted_after_its_image(self):
        merged, count = tables.merge_tables(HTML_BODY, MINERU_BODY)
        self.assertEqual(count, 1)
        self.assertRegex(merged, r"datasets\.svg\)\n\n<table><tr><td>HDFS</td><td>1\.58</td></tr></table>\n\nMiddle")
        self.assertNotIn("Other", merged)

    def test_table_two_does_not_match_table_one_or_three(self):
        merged, _ = tables.merge_tables(HTML_BODY, MINERU_BODY)
        self.assertRegex(merged, r"results\.svg\)\n\n!\[Fig")

    def test_caption_with_citation_brackets_is_matched(self):
        html = "![TABLE II: Results (Cowic [23] and LogArchive [24])](u.svg)\n"
        merged, count = tables.merge_tables(html, "TABLE II\nRESULTS\n\n<table><tr><td>7</td></tr></table>\n")
        self.assertEqual(count, 1)
        self.assertIn("<td>7</td>", merged)

    def test_figures_are_never_matched(self):
        merged, count = tables.merge_tables("![Fig. 1: Flow](u.png)\n", MINERU_BODY)
        self.assertEqual((merged, count), ("![Fig. 1: Flow](u.png)\n", 0))

    def test_numeric_labels(self):
        merged, count = tables.merge_tables("![Table 2: A](u.svg)\n", "Table 2: A\n\n<table><tr><td>9</td></tr></table>\n")
        self.assertEqual(count, 1)
        self.assertIn("<td>9</td>", merged)


class AssetPathTest(unittest.TestCase):
    def test_assets_live_under_raw_assets(self):
        out = Path("D:/kb/raw/log/p.md")
        self.assertEqual(cli._asset_dir(out), Path("D:/kb/raw/assets/p"))
        self.assertEqual(cli._asset_link(out, cli._asset_dir(out)), "../assets/p")

    def test_directly_under_raw(self):
        out = Path("D:/kb/raw/p.md")
        self.assertEqual(cli._asset_link(out, cli._asset_dir(out)), "assets/p")

    def test_outside_raw_uses_sibling_assets(self):
        out = Path("D:/tmp/p.md")
        self.assertEqual(cli._asset_dir(out), Path("D:/tmp/assets/p"))


class LocalizeTest(unittest.TestCase):
    def test_mineru_and_remote_images_are_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "assets" / "p"
            def save(url, path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
                return True
            with mock.patch.object(cli, "_save_image", side_effect=save):
                body, failed = cli._localize_images(
                    "![](images/a.jpg)\n![c](https://h/1v1/b.png)\n[link](https://h/page)\n", assets, "../assets/p")
            self.assertEqual(body, "![](../assets/p/a.jpg)\n![c](../assets/p/b.png)\n[link](https://h/page)\n")
            self.assertEqual(failed, 0)
            self.assertTrue((assets / "b.png").exists())

    def test_caption_with_brackets_is_localized(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(cli, "_save_image", return_value=True):
            body, _ = cli._localize_images("![T (A [23] b)](https://h/r.svg)\n", Path(tmp), "../a")
        self.assertEqual(body, "![T (A [23] b)](../a/r.svg)\n")

    def test_failed_download_keeps_remote_link(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(cli, "_save_image", return_value=False):
            body, failed = cli._localize_images("![c](https://h/b.png)\n", Path(tmp) / "a", "../a")
        self.assertEqual((body, failed), ("![c](https://h/b.png)\n", 1))


class HeaderTest(unittest.TestCase):
    def test_missing_numbers_are_counted(self):
        extraction = cli.Extraction("T", "alpha beta gamma delta 0.5", "s", "x")
        with tempfile.TemporaryDirectory() as tmp:
            cli._verify(extraction, ["alpha beta gamma delta 0.5 and 1.25 and 2.75"], Path(tmp) / "c.json")
        self.assertIn("PDF numbers not in text: 2", extraction.verification)


if __name__ == "__main__":
    unittest.main()
