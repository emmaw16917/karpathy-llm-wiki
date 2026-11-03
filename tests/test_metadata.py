import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llm_wiki import arxiv, cli, metadata, zotero  # noqa: E402
from llm_wiki.arxiv_html import convert  # noqa: E402
from llm_wiki.zotero import Item  # noqa: E402


def item(**kw):
    base = dict(key="K", item_type="conferencePaper", title="T", doi="10.1/x", url="", archive_id="", extra="",
                date="2019-11", first_author="Liu")
    base.update(kw)
    return Item(**base)


class VenueTest(unittest.TestCase):
    def test_parenthesized_acronym(self):
        it = item(conference="2019 34th IEEE/ACM International Conference on Automated Software Engineering (ASE)")
        self.assertEqual(metadata.venue(it, "2019-11"), "ASE 2019")

    def test_apostrophe_year_wins_over_date(self):
        it = item(conference="ICSE '24: IEEE/ACM 46th International Conference on Software Engineering")
        self.assertEqual(metadata.venue(it, "2023-12"), "ICSE 2024")

    def test_curly_apostrophe(self):
        self.assertEqual(metadata.venue(item(conference="APSys ’20: 11th Workshop"), "2020-08"), "APSys 2020")

    def test_proceedings_title_is_fallback(self):
        it = item(proceedings="2023 IEEE/ACM 45th International Conference on Software Engineering (ICSE)")
        self.assertEqual(metadata.venue(it, "2023-05"), "ICSE 2023")

    def test_known_journal(self):
        it = item(item_type="journalArticle", journal="Proceedings of the VLDB Endowment")
        self.assertEqual(metadata.venue(it, "2023-04"), "PVLDB 2023")

    def test_preprint(self):
        it = item(item_type="preprint", doi="10.48550/arXiv.2408.05760")
        self.assertEqual(metadata.venue(it, "2024-08-11"), "arXiv 2024")

    def test_unrecognized_name_is_kept_whole(self):
        it = item(proceedings="Proceedings of the Third International Workshop")
        self.assertEqual(metadata.venue(it, "2020-06"), "Proceedings of the Third International Workshop 2020")


class PublishedTest(unittest.TestCase):
    def test_parsed_date_wins(self):
        self.assertEqual(metadata.published(item(date="六月 14, 2020", parsed_date="2020-06-14")), "2020-06-14")

    def test_iso_date_without_parsed_date(self):
        self.assertEqual(metadata.published(item(date="2019-11")), "2019-11")

    def test_unparsable_date_is_empty(self):
        self.assertEqual(metadata.published(item(date="六月 14, 2020")), "")


class FrontMatterTest(unittest.TestCase):
    def test_renders_quoted_values_and_omits_empty(self):
        text = metadata.front_matter({"title": 'A: "b"', "authors": ["Ann Lee", "Bo"], "published": "2019-11", "doi": ""})
        self.assertEqual(text, '---\ntitle: "A: \\"b\\""\nauthors: ["Ann Lee", "Bo"]\npublished: 2019-11\n---\n')


class ItemFieldsTest(unittest.TestCase):
    def test_reads_extended_fields(self):
        raw = {"meta": {"parsedDate": "2020-06-14"}, "data": {
            "key": "K", "itemType": "conferencePaper", "title": "T", "citationKey": "kipf2020",
            "conferenceName": "C", "proceedingsTitle": "P", "publicationTitle": "J", "date": "x",
            "creators": [{"firstName": "Ann", "lastName": "Lee", "creatorType": "author"}, {"name": "Org", "creatorType": "author"},
                         {"firstName": "Ed", "lastName": "Itor", "creatorType": "editor"}]}}
        it = zotero._item(raw)
        self.assertEqual((it.citation_key, it.parsed_date, it.conference, it.proceedings, it.journal),
                         ("kipf2020", "2020-06-14", "C", "P", "J"))
        self.assertEqual(it.authors, ["Ann Lee", "Org"])


class EvidenceFrontMatterTest(unittest.TestCase):
    def run_check(self, raw_header):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw").mkdir()
            (root / "wiki").mkdir()
            (root / "raw" / "a.md").write_text(raw_header + "# A\n\n> Source: s\n\nnothing relevant\n", encoding="utf-8")
            (root / "wiki" / "a.md").write_text("# A\n\n> Raw: [a](../raw/a.md)\n\nPublished on 2019-11-05.\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_evidence.py"), str(root)],
                                  capture_output=True, encoding="utf-8")
        return done.stdout

    def test_front_matter_is_not_evidence(self):
        self.assertIn("1 fidelity suspect", self.run_check("---\npublished: 2019-11-05\n---\n\n"))

    def test_body_date_is_still_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw").mkdir()
            (root / "wiki").mkdir()
            (root / "raw" / "a.md").write_text("---\ntitle: x\n---\n\n# A\n\nOn 2019-11-05.\n", encoding="utf-8")
            (root / "wiki" / "a.md").write_text("# A\n\n> Raw: [a](../raw/a.md)\n\nOn 2019-11-05.\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_evidence.py"), str(root)],
                                  capture_output=True, encoding="utf-8")
        self.assertIn("0 fidelity suspect", done.stdout)


LISTING = """<article class="ltx_document"><figure class="ltx_float_algorithm"><figcaption class="ltx_caption">Algorithm 1 GA</figcaption>
<div class="ltx_listing">{}</div></figure></article>"""


def listing(*lines):
    return LISTING.format("".join(
        f'<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">{i}:</span> {line}</div>'
        for i, line in enumerate(lines, 1)))


class PseudocodeTest(unittest.TestCase):
    def test_indentation_is_rebuilt_in_a_code_block(self):
        result = convert(listing(
            "init <math alttext='k=0' display='inline'></math>",
            '<span class="ltx_font_bold">while</span> running <span class="ltx_font_bold">do</span>',
            '<span class="ltx_font_bold">if</span> a <span class="ltx_font_bold">then</span>', "step",
            '<span class="ltx_font_bold">else</span>', "other",
            '<span class="ltx_font_bold">end</span> <span class="ltx_font_bold">if</span>',
            '<span class="ltx_font_bold">end</span> <span class="ltx_font_bold">while</span>',
            '<span class="ltx_font_bold">return</span> k'), "https://x/")
        self.assertIn(
            "```text\n1: init $k=0$\n2: while running do\n3:     if a then\n4:         step\n5:     else\n"
            "6:         other\n7:     end if\n8: end while\n9: return k\n```", result.markdown)
        self.assertEqual((result.indented_listings, result.flat_listings), (1, 0))

    def test_one_line_conditional_does_not_open_a_block(self):
        md = convert(listing("for i do", "if a then return b", "step", "end for"), "https://x/").markdown
        self.assertIn("2:     if a then return b\n3:     step\n4: end for", md)

    def test_unbalanced_listing_stays_flat_and_is_counted(self):
        result = convert(listing("while a do", "step"), "https://x/")
        self.assertIn("1: while a do\n2: step", result.markdown)
        self.assertEqual((result.indented_listings, result.flat_listings), (0, 1))

    def test_listing_without_blocks_is_not_counted(self):
        result = convert(listing("step", "return k"), "https://x/")
        self.assertEqual((result.indented_listings, result.flat_listings), (0, 0))


class FileNamingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paper = arxiv.Paper("2401.00001", 2, "Great", ["Ann Lee"], "2024-01-05")
        self.page = '<article class="ltx_document"><h1 class="ltx_title_document">T</h1><p>Body</p></article>'

    def run_cli(self, *args, found=None):
        with mock.patch.object(cli, "_reference_pages", return_value=None), \
                mock.patch.object(cli.openalex, "find_published_version", return_value=None), \
                mock.patch.object(cli.zotero, "find", return_value=found), \
                mock.patch.object(cli.arxiv, "lookup", return_value=self.paper), \
                mock.patch.object(cli.arxiv, "fetch_html", return_value=(self.page, "https://x/")):
            return cli.main([*args, "--config", str(self.root / "none")])

    def preprint(self):
        return item(item_type="preprint", doi="10.48550/arXiv.2401.00001", citation_key="leeGreat2024",
                    title="Great", authors=["Ann Lee"], date="2024-01-05")

    def test_directory_out_uses_citekey_and_writes_front_matter(self):
        topic = self.root / "raw" / "logs"
        self.assertEqual(self.run_cli("--key", "K", "--out", str(topic), found=self.preprint()), 0)
        text = (topic / "leeGreat2024.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith('---\ncitekey: "leeGreat2024"\nzotero_key: "K"\ntitle: "Great"\n'))
        for line in ('authors: ["Ann Lee"]', "published: 2024-01-05", 'venue: "arXiv 2024"',
                     'doi: "10.48550/arXiv.2401.00001"', 'arxiv: "2401.00001"'):
            self.assertIn(line, text)
        self.assertIn("---\n\n# T\n\n> Source: https://arxiv.org/abs/2401.00001v2\n> Collected:", text)
        for removed in ("> Published:", "> Zotero:", "> DOI:"):
            self.assertNotIn(removed, text)

    def test_venue_flag_overrides(self):
        topic = self.root / "raw"
        self.assertEqual(self.run_cli("--key", "K", "--out", str(topic), "--venue", "aiDM 2020", found=self.preprint()), 0)
        self.assertIn('venue: "aiDM 2020"', (topic / "leeGreat2024.md").read_text(encoding="utf-8"))

    def test_arxiv_only_uses_id_as_name(self):
        topic = self.root / "raw"
        self.assertEqual(self.run_cli("--arxiv", "2401.00001", "--out", str(topic)), 0)
        text = (topic / "arxiv-2401.00001.md").read_text(encoding="utf-8")
        self.assertIn('authors: ["Ann Lee"]', text)
        self.assertIn('venue: "arXiv 2024"', text)
        self.assertNotIn("citekey", text)

    def test_item_without_citekey_is_refused_for_directory_out(self):
        self.assertEqual(self.run_cli("--key", "K", "--out", str(self.root / "raw"), found=item()), 2)


if __name__ == "__main__":
    unittest.main()
