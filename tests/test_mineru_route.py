import io
import os
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_wiki import cli, mineru, openalex, pdf_check, zotero  # noqa: E402
from llm_wiki.zotero import Item  # noqa: E402


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


class UnpackTest(unittest.TestCase):
    def test_rewrites_image_links_and_blocks_traversal(self):
        data = make_zip({
            "full.md": "# T\n\n![](images/a.jpg)\n\nA1 ![x](images/b.jpg)\n",
            "images/a.jpg": b"A",
            "images/b.jpg": b"B",
            "images/../../evil.txt": b"E",
            "other.json": b"{}",
        })
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "out" / "p.assets"
            md = mineru.unpack(data, assets)
            self.assertIn("![](p.assets/a.jpg)", md)
            self.assertIn("![x](p.assets/b.jpg)", md)
            self.assertEqual(sorted(p.name for p in assets.iterdir()), ["a.jpg", "b.jpg"])
            self.assertFalse((Path(tmp) / "evil.txt").exists())
            self.assertFalse((Path(tmp) / "out" / "evil.txt").exists())

    def test_missing_markdown_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(mineru.MineruError):
            mineru.unpack(make_zip({"x.json": b"{}"}), Path(tmp) / "a")


class UploadTest(unittest.TestCase):
    def test_put_sends_no_content_type(self):
        conn = mock.MagicMock()
        conn.getresponse.return_value.status = 200
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(mineru.http.client, "HTTPSConnection", return_value=conn):
            path = Path(tmp) / "a.pdf"
            path.write_bytes(b"%PDF")
            mineru.put_signed("https://b.example/p/a.pdf?sig=1", path)
        conn.request.assert_called_once_with("PUT", "/p/a.pdf?sig=1", body=b"%PDF")

    def test_put_failure_does_not_leak_signed_url(self):
        conn = mock.MagicMock()
        conn.getresponse.return_value.status = 403
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(mineru.http.client, "HTTPSConnection", return_value=conn):
            path = Path(tmp) / "a.pdf"
            path.write_bytes(b"%PDF")
            with self.assertRaises(mineru.MineruError) as caught:
                mineru.put_signed("https://b.example/p/a.pdf?sig=SECRET", path)
        self.assertNotIn("SECRET", str(caught.exception))


class DownloadTest(unittest.TestCase):
    @staticmethod
    def response(read):
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.side_effect = read
        return resp

    def test_truncated_download_is_retried(self):
        responses = [self.response(mineru.http.client.IncompleteRead(b"x", 9)), self.response([b"OK"])]
        with mock.patch.object(mineru.net, "urlopen", side_effect=responses), \
                mock.patch.object(mineru.time, "sleep"):
            self.assertEqual(mineru.Client._download("https://x/a.zip"), b"OK")

    def test_repeated_truncation_becomes_mineru_error(self):
        truncated = mineru.http.client.IncompleteRead(b"x", 9)
        with mock.patch.object(mineru.net, "urlopen", side_effect=lambda *a, **k: self.response(truncated)), \
                mock.patch.object(mineru.time, "sleep"), self.assertRaises(mineru.MineruError):
            mineru.Client._download("https://x/a.zip")

    def test_corrupt_zip_is_mineru_error(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(mineru.MineruError):
            mineru.unpack(b"not a zip", Path(tmp) / "a")


class AnnotationCheckTest(unittest.TestCase):
    def check(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.pdf"
            path.write_bytes(data)
            return pdf_check.embedded_annotations(path)

    def test_plain_annotation(self):
        self.assertEqual(self.check(b"%PDF 1 0 obj<</Subtype /Highlight>>endobj"), {"Highlight"})

    def test_annotation_inside_compressed_object_stream(self):
        stream = zlib.compress(b"<</Type/Annot/Subtype/FreeText>>")
        self.assertEqual(self.check(b"%PDF 1 0 obj<<>>stream\n" + stream + b"\nendstream"), {"FreeText"})

    def test_links_and_clean_files_do_not_count(self):
        self.assertEqual(self.check(b"%PDF <</Subtype /Link>> <</Subtype /Widget>>"), set())


class OpenAlexTest(unittest.TestCase):
    def work(self, *locations, best=None):
        return {"best_oa_location": best, "locations": list(locations)}

    def test_only_published_pdf_is_returned(self):
        preprint = {"pdf_url": "https://arxiv.org/pdf/1", "version": "submittedVersion"}
        published = {"pdf_url": "https://pub/x.pdf", "version": "publishedVersion"}
        self.assertEqual(openalex.published_pdf(self.work(preprint, published, best=preprint)), "https://pub/x.pdf")
        self.assertIsNone(openalex.published_pdf(self.work(preprint, best=preprint)))
        self.assertIsNone(openalex.published_pdf(self.work({"pdf_url": None, "version": "publishedVersion"})))


class AttachmentTest(unittest.TestCase):
    def child(self, key, mode, ctype, path="", filename=""):
        return {"key": key, "data": {"itemType": "attachment", "linkMode": mode, "contentType": ctype,
                                     "path": path, "filename": filename}}

    def test_prefers_stored_pdf_and_resolves_path(self):
        children = [
            self.child("H", "imported_url", "text/html", filename="a.html"),
            self.child("L", "linked_file", "application/pdf", path="D:/x/linked.pdf"),
            self.child("S", "imported_file", "application/pdf", filename="s.pdf"),
        ]
        with mock.patch.object(zotero, "_get", return_value=children):
            att = zotero.pdf_attachment("u", "ITEM", "D:/Z")
        self.assertEqual(att.key, "S")
        self.assertEqual(att.path, Path("D:/Z/storage/S/s.pdf"))

    def test_linked_pdf_used_when_alone_and_none_without_pdf(self):
        with mock.patch.object(zotero, "_get", return_value=[self.child("L", "linked_file", "application/pdf", path="D:/x/l.pdf")]):
            self.assertEqual(zotero.pdf_attachment("u", "I", "D:/Z").path, Path("D:/x/l.pdf"))
        with mock.patch.object(zotero, "_get", return_value=[self.child("H", "imported_url", "text/html", filename="a")]):
            self.assertIsNone(zotero.pdf_attachment("u", "I", "D:/Z"))


class RouteTest(unittest.TestCase):
    """Order: arXiv HTML, public PDF URL, then the Zotero PDF."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "raw" / "t" / "p.md"
        self.pdf = self.root / "local.pdf"
        self.pdf.write_bytes(b"%PDF clean")
        self.config = self.root / "c.json"
        self.config.write_text('{"mineru": {"api_token": "TOKEN"}, "zotero": {"data_dir": "D:/Z"}}', encoding="utf-8")
        self.client = mock.MagicMock()
        self.client.parse_url.side_effect = self.fake_parse
        self.client.parse_file.side_effect = self.fake_parse
        self.item = Item("K", "conferencePaper", "Zotero Title", "10.1/x", "", "", "", "2020", "Sun")

    @staticmethod
    def fake_parse(_source, assets):
        return "# Zotero Title\n\nBody 1.5\n"

    def run_cli(self, *extra, oa=None, attachment=True, item=None):
        att = zotero.Attachment("ATT", self.pdf) if attachment else None
        with mock.patch.dict(os.environ), \
                mock.patch.object(cli, "_reference_pages", return_value=None), \
                mock.patch.object(cli.zotero, "find", return_value=item or self.item), \
                mock.patch.object(cli.zotero, "pdf_attachment", return_value=att), \
                mock.patch.object(cli.arxiv, "search", return_value=[]), \
                mock.patch.object(cli.openalex, "find_published_pdf", return_value=oa), \
                mock.patch.object(cli.mineru, "Client", return_value=self.client):
            os.environ.pop("MINERU_API_TOKEN", None)
            return cli.main(["--key", "K", "--out", str(self.out), "--config", str(self.config), *extra])

    def test_public_pdf_preferred_over_upload(self):
        self.assertEqual(self.run_cli(oa="https://pub/x.pdf"), 0)
        self.client.parse_url.assert_called_once()
        self.client.parse_file.assert_not_called()
        text = self.out.read_text(encoding="utf-8")
        self.assertIn("> Source: https://pub/x.pdf", text)
        self.assertIn("> Extractor: mineru-vlm (url)", text)

    def test_falls_back_to_upload_and_records_original(self):
        self.client.parse_url.side_effect = mineru.MineruError("timeout")
        self.assertEqual(self.run_cli(oa="https://pub/x.pdf"), 0)
        self.client.parse_file.assert_called_once()
        text = self.out.read_text(encoding="utf-8")
        self.assertIn("> Source: https://doi.org/10.1/x", text)
        self.assertIn("> Extractor: mineru-vlm (upload)", text)
        self.assertIn("> Original: Zotero attachment ATT, sha256:", text)
        self.assertTrue(text.startswith("# Zotero Title\n"))
        self.assertIn("Body 1.5", text)
        self.assertEqual(text.count("# Zotero Title"), 1)

    def test_item_without_identifier_needs_explicit_permission(self):
        bare = Item("K", "report", "Private Draft", "", "", "", "", "", "Sun")
        self.assertEqual(self.run_cli(item=bare), 3)
        self.client.parse_file.assert_not_called()
        self.assertFalse(self.out.exists())
        self.assertEqual(self.run_cli("--allow-upload", item=bare), 0)
        self.client.parse_file.assert_called_once()

    def test_embedded_annotations_block_upload_unless_allowed(self):
        self.pdf.write_bytes(b"%PDF <</Subtype /Highlight>>")
        self.assertEqual(self.run_cli(), 3)
        self.client.parse_file.assert_not_called()
        self.assertEqual(self.run_cli("--allow-annotated"), 0)

    def test_no_token_means_no_route(self):
        self.config.write_text('{"mineru": {"api_token": ""}}', encoding="utf-8")
        self.assertEqual(self.run_cli(), 3)
        self.assertFalse(self.out.exists())

    def test_no_attachment_means_no_route(self):
        self.assertEqual(self.run_cli(attachment=False), 3)


if __name__ == "__main__":
    unittest.main()
