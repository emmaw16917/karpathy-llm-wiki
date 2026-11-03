import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_wiki import latex_source  # noqa: E402
from llm_wiki.arxiv_html import convert, indent_from_tokens, indent_listing  # noqa: E402

HEADER = r"\documentclass{a}\usepackage[ruled]{algorithm2e}\begin{document}"


def blocks(body):
    return latex_source.algorithm_blocks({"m.tex": HEADER + r"\begin{algorithm}" + body + r"\end{algorithm}"})


class ParseTest(unittest.TestCase):
    def test_real_paper_shape(self):
        body = r"""[htb]
\caption{Some \textit{caption}.}
\label{alg:x}
\SetAlgoLined
\KwIn{Pool $\mathbf{C}$, set \{a\}}
\KwOut{Sample}

\textcolor{gray}{\texttt{\# Sample}} \\
$a$ $\sim$ $b$\\

\If{$tg = 1$}{
    $x$ \textcolor{gray}{\texttt{\# note}} \\
    $y$
}
\If{$a$ or $b$}{
    $z$ \\
    \If{$c$}{
        $w$
    }
    $v$
}

$u$, $t$
"""
        self.assertEqual(blocks(body), [[
            "line", "line", "line", "line",
            "open", "line", "line", "close:if",
            "open", "line", "open", "line", "close:if", "line", "close:if",
            "line"]])

    def test_semicolon_statements_and_loops(self):
        self.assertEqual(blocks(r"\For{$i$}{a\; b\;}\While{c}{d\;}\ForEach{e}{f\;}"), [[
            "open", "line", "line", "close:for", "open", "line", "close:while", "open", "line", "close:for"]])

    def test_chained_conditionals(self):
        self.assertEqual(blocks(r"\uIf{a}{b\;}\uElseIf{c}{d\;}\Else{e\;}"), [[
            "open", "line", "middle", "line", "middle", "line", "close:if"]])
        self.assertEqual(blocks(r"\eIf{a}{b\;}{c\;}"), [["open", "line", "middle", "line", "close:if"]])

    def test_one_line_forms_and_repeat(self):
        self.assertEqual(blocks(r"\lIf{a}{b}\lFor{c}{d}\Repeat{e}{f\;}"), [["line", "line", "open", "line", "close:until"]])

    def test_function_and_setup_commands_are_handled(self):
        self.assertEqual(blocks(r"\DontPrintSemicolon\SetKwFunction{F}{f}\Fn{\F{x}}{a\;\KwRet{b}\;}"), [[
            "open", "line", "line", "close:function"]])

    def test_comment_only_statement_counts(self):
        self.assertEqual(blocks(r"\tcc{note}a\;"), [["line", "line"]])

    def test_escaped_braces_do_not_break_blocks(self):
        self.assertEqual(blocks(r"\If{\{a\}}{b \{c\}\;}"), [["open", "line", "close:if"]])

    def test_document_order_with_algorithmic(self):
        text = HEADER + r"\begin{algorithm}a\;\end{algorithm}\begin{algorithm}\begin{algorithmic}\State b\end{algorithmic}\end{algorithm}"
        self.assertEqual(latex_source.algorithm_blocks({"m.tex": text}), [["line"], ["line"]])

    def test_without_the_package_plain_algorithm_is_ignored(self):
        text = r"\documentclass{a}\begin{algorithm}\includegraphics{x}\end{algorithm}"
        self.assertEqual(latex_source.algorithm_blocks({"m.tex": text}), [])

    def test_unbalanced_braces_give_no_tokens(self):
        self.assertEqual(blocks(r"\If{a}{b"), [[]])


class ListingMarkupTest(unittest.TestCase):
    def test_emphasis_markers_are_dropped_but_math_stars_stay(self):
        page = ('<article class="ltx_document"><div class="ltx_listing"><div class="ltx_listingline">1 '
                '<span class="ltx_font_bold">if</span> <em class="ltx_emph">a</em> '
                '<math alttext="N*2" display="inline"></math></div></div></article>')
        self.assertIn("1 if a $N*2$\n", convert(page, "https://x/").markdown)


class BibliographyTest(unittest.TestCase):
    def page(self, tag):
        return ('<article class="ltx_document"><ul><li class="ltx_bibitem"><span class="ltx_tag ltx_tag_bibitem">'
                f'{tag}</span><span class="ltx_bibblock">Text.</span></li></ul></article>')

    def test_bracketed_number_is_not_doubled(self):
        self.assertIn("- [1] Text.", convert(self.page("[1]"), "https://x/").markdown)

    def test_author_year_tag_gets_brackets(self):
        self.assertIn("- [Lee (2020)] Text.", convert(self.page("Lee (2020)"), "https://x/").markdown)


class NoColonLabelTest(unittest.TestCase):
    LINES = ["Input: x", "Output: y", "1 # note", "2 $a$", "3 if b then", "4 c", "5 end if"]

    def test_tokens_align_with_labels_without_colon(self):
        tokens = ["line", "line", "line", "line", "open", "line", "close:if"]
        self.assertEqual(indent_from_tokens(self.LINES, tokens)[4:], ["3 if b then", "4     c", "5 end if"])

    def test_keywords_work_with_labels_without_colon(self):
        lines, state = indent_listing(self.LINES)
        self.assertEqual(state, "indented")
        self.assertEqual(lines[4:], ["3 if b then", "4     c", "5 end if"])

    def test_hidden_ends_use_source(self):
        result = indent_from_tokens(["1 if a then", "2 b", "3 c"], ["open", "line", "close:if", "line"])
        self.assertEqual(result, ["1 if a then", "2     b", "3 c"])

    def test_convert_uses_algorithm2e_blocks(self):
        page = ('<article class="ltx_document"><div class="ltx_listing">'
                '<div class="ltx_listingline">1 if a then</div><div class="ltx_listingline">2 b</div>'
                '<div class="ltx_listingline">3 c</div></div></article>')
        tokens = blocks(r"\If{a}{b\;}c\;")
        result = convert(page, "https://x/", tokens)
        self.assertIn("1 if a then\n2     b\n3 c", result.markdown)
        self.assertEqual(result.source_listings, 1)


if __name__ == "__main__":
    unittest.main()
