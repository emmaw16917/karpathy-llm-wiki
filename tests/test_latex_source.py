import gzip
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_wiki import arxiv, cli, latex_source, openalex  # noqa: E402
from llm_wiki.arxiv_html import convert, indent_from_tokens  # noqa: E402
from llm_wiki.zotero import Item  # noqa: E402

MAIN = r"""\documentclass{article}
\input{math}
\begin{document}
\input{Sections/method}
% \input{Sections/outdated}
\end{document}
"""
METHOD = r"""\begin{algorithmic}[1]
\State init
\While{running}
  \For{each $x$}
    \State step % comment \If
  \EndFor
  \If{a}
    \State b
  \Else
    \State c
  \EndIf
\EndWhile
\State \Return k
\end{algorithmic}
"""
OUTDATED = r"\begin{algorithmic}\State old\end{algorithmic}"
TOKENS = ["line", "open", "open", "line", "close:for", "open", "line", "middle", "line",
          "close:if", "close:while", "line"]


def tar_gz(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class SourceTest(unittest.TestCase):
    def test_follows_inputs_from_main_and_skips_unused_files(self):
        files = latex_source.read_tex_files(tar_gz({
            "main.tex": MAIN, "math.tex": "", "Sections/method.tex": METHOD, "Sections/outdated.tex": OUTDATED,
            "../evil.tex": OUTDATED}))
        blocks = latex_source.algorithm_blocks(files)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0], TOKENS)

    def test_single_gzipped_file(self):
        files = latex_source.read_tex_files(gzip.compress((r"\documentclass{a}\begin{document}" + METHOD).encode()))
        self.assertEqual(len(latex_source.algorithm_blocks(files)), 1)

    def test_garbage_gives_nothing(self):
        self.assertEqual(latex_source.algorithm_blocks(latex_source.read_tex_files(b"not an archive")), [])

    def test_uppercase_commands(self):
        text = r"\documentclass{a}\begin{algorithmic}\FOR{x}\STATE y\ENDFOR\RETURN z\end{algorithmic}"
        self.assertEqual(latex_source.algorithm_blocks({"m.tex": text}), [["open", "line", "close:for", "line"]])


class AlignTest(unittest.TestCase):
    def test_omitted_end_lines_are_resolved(self):
        lines = ["1: init", "2: while r do", "3: for x do", "4: step", "5: if a then", "6: b", "7: else", "8: c",
                 "9: end while", "10: return k"]
        self.assertEqual(indent_from_tokens(lines, TOKENS), [
            "1: init", "2: while r do", "3:     for x do", "4:         step", "5:     if a then", "6:         b",
            "7:     else", "8:         c", "9: end while", "10: return k"])

    def test_printed_end_lines_are_consumed(self):
        lines = ["1: for x do", "2: y", "3: end for"]
        self.assertEqual(indent_from_tokens(lines, ["open", "line", "close"]), ["1: for x do", "2:     y", "3: end for"])

    def test_line_count_mismatch_is_rejected(self):
        self.assertIsNone(indent_from_tokens(["1: a", "2: b", "3: c"], ["line", "line"]))
        self.assertIsNone(indent_from_tokens(["1: a"], ["line", "line"]))


LISTING = """<article class="ltx_document"><div class="ltx_listing">{}</div></article>"""


def listing(*lines):
    return LISTING.format("".join(f'<div class="ltx_listingline">{i}: {l}</div>' for i, l in enumerate(lines, 1)))


class ConvertWithSourceTest(unittest.TestCase):
    def test_source_structure_wins_and_is_counted(self):
        result = convert(listing("for x do", "y", "z"), "https://x/", [["open", "line", "close", "line"]])
        self.assertIn("1: for x do\n2:     y\n3: z", result.markdown)
        self.assertEqual((result.source_listings, result.indented_listings, result.flat_listings), (1, 0, 0))

    def test_unmatched_block_is_skipped_without_shifting_later_ones(self):
        page = LISTING.format('<div class="ltx_listingline">1: for a do</div><div class="ltx_listingline">2: b</div>')
        blocks = [["line"], ["open", "line", "close"]]
        result = convert(page, "https://x/", blocks)
        self.assertIn("1: for a do\n2:     b", result.markdown)
        self.assertEqual(result.source_listings, 1)

    def test_no_match_falls_back_to_keywords(self):
        result = convert(listing("for x do", "y", "end for"), "https://x/", [["line"]])
        self.assertEqual((result.source_listings, result.indented_listings), (0, 1))


class PublishedVersionTest(unittest.TestCase):
    def test_finds_published_location(self):
        work = {"doi": "https://doi.org/10.1145/3691620.3695474", "locations": [
            {"version": "publishedVersion", "source": {"display_name": "ASE"}},
            {"version": "submittedVersion", "source": {"display_name": "arXiv (Cornell University)"}}]}
        self.assertEqual(openalex.published_version(work), ("10.1145/3691620.3695474", "ASE"))

    def test_preprint_only_work_gives_none(self):
        work = {"doi": "https://doi.org/10.48550/arxiv.2310.04451",
                "locations": [{"version": "submittedVersion", "source": {"display_name": "arXiv"}}]}
        self.assertIsNone(openalex.published_version(work))


class ReminderTest(unittest.TestCase):
    def run_cli(self, item_type, doi, found):
        page = '<article class="ltx_document"><h1 class="ltx_title_document">T</h1><p>Body</p></article>'
        paper = arxiv.Paper("2408.05760", 1, "T", ["Ann Yu"], "2024-08-11")
        it = Item("K", item_type, "T", doi, "", "arXiv:2408.05760", "", "2024", "Yu", citation_key="yuT2024")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cli, "_reference_pages", return_value=None), \
                mock.patch.object(cli.zotero, "find", return_value=it), \
                mock.patch.object(cli.arxiv, "lookup", return_value=paper), \
                mock.patch.object(cli.arxiv, "fetch_html", return_value=(page, "https://x")), \
                mock.patch.object(cli.openalex, "find_published_version", return_value=found) as lookup:
            self.assertEqual(cli.main(["--key", "K", "--out", tmp, "--config", tmp + "/none"]), 0)
            return (Path(tmp) / "yuT2024.md").read_text(encoding="utf-8"), lookup

    def test_preprint_with_published_version_gets_a_note_and_keeps_arxiv_text(self):
        text, _ = self.run_cli("preprint", "10.48550/arXiv.2408.05760", ("10.1145/1", "ASE"))
        self.assertIn("> Published-version: https://doi.org/10.1145/1 (ASE, per OpenAlex)", text)
        self.assertIn("> Source: https://arxiv.org/abs/2408.05760v1", text)
        self.assertIn('doi: "10.48550/arXiv.2408.05760"', text)

    def test_no_note_when_none_found(self):
        text, _ = self.run_cli("preprint", "10.48550/arXiv.2408.05760", None)
        self.assertNotIn("Published-version", text)

    def test_published_item_is_not_looked_up(self):
        _, lookup = self.run_cli("conferencePaper", "10.1145/1", ("10.1145/1", "ASE"))
        lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
