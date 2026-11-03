import base64
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_wiki import cli, metadata, web, zotero  # noqa: E402
from llm_wiki.zotero import Item  # noqa: E402


class CitekeyTest(unittest.TestCase):
    def test_author_title_year(self):
        self.assertEqual(metadata.make_citekey("Simon Willison", "The New Claude 3 Model Family", "2024-03-04", "x.net"),
                         "willisonNewClaude32024")

    def test_missing_author_uses_site(self):
        self.assertEqual(metadata.make_citekey("", "How Logs Work", "", "blog.csdn.net"), "csdnHowLogsWork")

    def test_non_ascii_title_gets_stable_hash(self):
        first = metadata.make_citekey("", "Qt信号与槽机制解析", "", "blog.csdn.net")
        self.assertRegex(first, r"^csdnQt[0-9a-f]{6}$")
        self.assertEqual(first, metadata.make_citekey("", "Qt信号与槽机制解析", "", "blog.csdn.net"))

    def test_poor_zotero_keys(self):
        for key in ("zotero-29", "QtXinHaoYuCaoJiZhiJieXiCSDNBoKe", ""):
            self.assertFalse(metadata.good_citekey(key), key)
        self.assertTrue(metadata.good_citekey("liuLogzipExtractingHidden2019"))


class PageTest(unittest.TestCase):
    def parsed(self, **kw):
        base = {"title": "T‍​", "author": "", "published": "", "site": "", "domain": "a.org", "content": "Body",
                "metaTags": [], "schemaOrgData": []}
        base.update(kw)
        return base

    def test_title_is_cleaned_and_site_falls_back_to_domain(self):
        page = web.to_page(self.parsed(), "https://a.org/p")
        self.assertEqual((page.title, page.site), ("T", "a.org"))

    def test_zero_width_only_title_is_empty(self):
        self.assertEqual(web.to_page(self.parsed(title="‍​ ⁠"), "https://a.org/p").title, "")

    def test_date_comes_from_published_then_meta_then_schema(self):
        self.assertEqual(web.to_page(self.parsed(published="2024-03-04T10:00:00Z"), "u").published, "2024-03-04")
        meta = [{"property": "article:published_time", "content": "2023-01-02T00:00:00"}]
        self.assertEqual(web.to_page(self.parsed(metaTags=meta), "u").published, "2023-01-02")
        self.assertEqual(web.to_page(self.parsed(schemaOrgData=[{"datePublished": "2022-05-06"}]), "u").published, "2022-05-06")
        self.assertEqual(web.to_page(self.parsed(published="yesterday"), "u").published, "")

    def test_relative_images_become_absolute(self):
        page = web.to_page(self.parsed(content="![a](/i/x.png) ![b](data:image/png;base64,QQ==) ![c](https://o/y.png)"),
                           "https://a.org/p/q")
        self.assertIn("![a](https://a.org/i/x.png)", page.markdown)
        self.assertIn("![b](data:image/png;base64,QQ==)", page.markdown)
        self.assertIn("![c](https://o/y.png)", page.markdown)


class DateFromUrlTest(unittest.TestCase):
    def test_month_name_day(self):
        self.assertEqual(web.date_from_url("https://simonwillison.net/2024/Mar/4/claude-3/"), "2024-03-04")

    def test_numeric_month_and_day(self):
        self.assertEqual(web.date_from_url("https://a.org/blog/2023/01/02/post.html"), "2023-01-02")
        self.assertEqual(web.date_from_url("https://a.org/2023/7/9"), "2023-07-09")

    def test_year_and_month_only(self):
        self.assertEqual(web.date_from_url("https://a.org/2022/11/post"), "2022-11")

    def test_ignores_invalid_dates_and_other_paths(self):
        for url in ("https://a.org/2024/13/01/x", "https://a.org/2024/00/10/x", "https://a.org/2024/05/32/x",
                    "https://a.org/posts/hello", "https://a.org/1999/09/09/x"):
            self.assertEqual(web.date_from_url(url), "", url)

    def test_query_string_is_not_a_date(self):
        self.assertEqual(web.date_from_url("https://a.org/page?date=2024/03/04"), "")


class DataImageTest(unittest.TestCase):
    def test_embedded_image_is_saved_to_assets(self):
        data = base64.b64encode(b"PNGDATA").decode()
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "assets" / "p"
            body, failed = cli._localize_images(f"![x](data:image/png;base64,{data})\n", assets, "../assets/p")
            self.assertEqual(failed, 0)
            self.assertNotIn("base64", body)
            name = body.split("../assets/p/")[1].split(")")[0]
            self.assertTrue(name.endswith(".png"))
            self.assertEqual((assets / name).read_bytes(), b"PNGDATA")


class RouteTest(unittest.TestCase):
    PAGE = web.Page("My Post", "Ann Lee", "2024-03-04", "Ann's Blog", "Body 1.5\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.snapshot = self.root / "s.html"
        self.snapshot.write_text("<html>", encoding="utf-8")

    def run_cli(self, *args, found=None, att=None):
        with mock.patch.object(cli.zotero, "find", return_value=found), \
                mock.patch.object(cli.zotero, "html_attachment", return_value=att), \
                mock.patch.object(cli.web, "from_file", return_value=self.PAGE) as from_file, \
                mock.patch.object(cli.web, "from_url", return_value=self.PAGE) as from_url:
            self.from_file, self.from_url = from_file, from_url
            return cli.main([*args, "--out", str(self.root / "raw" / "blogs"), "--config", str(self.root / "none")])

    def web_item(self, **kw):
        base = dict(key="K", item_type="webpage", title="Zotero Title", doi="", url="https://a.org/p", archive_id="",
                    extra="", date="", first_author="")
        base.update(kw)
        return Item(**base)

    def read(self, name):
        return (self.root / "raw" / "blogs" / name).read_text(encoding="utf-8")

    def test_url_generates_citekey_and_venue(self):
        self.assertEqual(self.run_cli("--url", "https://a.org/p"), 0)
        text = self.read("leeMyPost2024.md")
        for line in ('citekey: "leeMyPost2024"', 'title: "My Post"', 'authors: ["Ann Lee"]', "published: 2024-03-04",
                     'venue: "Ann\'s Blog"', 'url: "https://a.org/p"', "> Source: https://a.org/p",
                     "> Extractor: defuddle (url)", "Body 1.5"):
            self.assertIn(line, text)
        self.assertNotIn("Verification", text)

    def test_url_date_fills_missing_publication_date(self):
        page = web.Page("My Post", "Ann Lee", "", "Ann's Blog", "Body 1.5\n")
        with mock.patch.object(cli.web, "from_url", return_value=page):
            code = cli.main(["--url", "https://a.org/2024/03/04/my-post", "--config", str(self.root / "none"),
                             "--out", str(self.root / "raw" / "blogs")])
        self.assertEqual(code, 0)
        text = self.read("leeMyPost2024.md")
        self.assertIn("published: 2024-03-04", text)
        self.assertIn('citekey: "leeMyPost2024"', text)

    def test_zotero_snapshot_is_preferred_and_good_key_kept(self):
        item = self.web_item(citation_key="leePost2024", authors=["Zoe Ng"], parsed_date="2020-01-02")
        self.assertEqual(self.run_cli("--key", "K", found=item, att=zotero.Attachment("A", self.snapshot)), 0)
        self.from_file.assert_called_once()
        self.from_url.assert_not_called()
        text = self.read("leePost2024.md")
        for line in ('zotero_key: "K"', 'title: "Zotero Title"', 'authors: ["Zoe Ng"]', "published: 2020-01-02",
                     "> Extractor: defuddle (zotero snapshot)"):
            self.assertIn(line, text)

    def test_poor_zotero_key_is_replaced(self):
        item = self.web_item(citation_key="zotero-29", title="‍​")
        self.assertEqual(self.run_cli("--key", "K", found=item), 0)
        self.from_url.assert_called_once()
        self.assertIn('title: "My Post"', self.read("leeMyPost2024.md"))

    def test_name_and_venue_override(self):
        self.assertEqual(self.run_cli("--url", "https://a.org/p", "--name", "myKey", "--venue", "Blog X"), 0)
        self.assertIn('venue: "Blog X"', self.read("myKey.md"))

    def test_raw_assets_is_not_a_topic(self):
        code = cli.main(["--url", "https://a.org/p", "--name", "k", "--config", str(self.root / "n"),
                         "--out", str(self.root / "raw" / "assets")])
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "raw").exists())

    def test_failed_extraction_writes_nothing(self):
        with mock.patch.object(cli.web, "from_url", side_effect=web.WebError("no node")):
            code = cli.main(["--url", "https://a.org/p", "--out", str(self.root / "raw"), "--config", str(self.root / "n")])
        self.assertEqual(code, 3)
        self.assertFalse((self.root / "raw").exists())


if __name__ == "__main__":
    unittest.main()
