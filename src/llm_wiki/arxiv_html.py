"""Convert arXiv's LaTeXML-generated HTML to Markdown.

Math comes from each <math> element's alttext, which holds the LaTeX.
Tables stay as compact HTML so merged cells survive.
"""
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
BLOCK = {"table", "figure", "div", "section", "article", "ul", "ol", "li", "p", "pre", "blockquote",
         "h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"nav", "header", "footer", "script", "style", "button"}
SKIP_CLASSES = {"ltx_TOC", "ltx_page_footer", "ltx_note_mark", "ltx_author_notes", "ltx_tag_item", "ltx_listing_data"}


@dataclass
class Result:
    markdown: str
    title: str
    errors: int
    tables: int
    equations: int


class Node:
    def __init__(self, tag, attrs=None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children = []
        self.classes = set((self.attrs.get("class") or "").split())

    def nodes(self):
        return [c for c in self.children if isinstance(c, Node)]

    def walk(self):
        for child in self.nodes():
            yield child
            yield from child.walk()

    def find(self, predicate):
        return next((n for n in self.walk() if predicate(n)), None)

    def has_class(self, name):
        return name in self.classes


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _skipped(node):
    return node.tag in SKIP_TAGS or bool(node.classes & SKIP_CLASSES)


class _Renderer:
    def __init__(self, base_url):
        self.base_url = base_url
        self.errors = 0
        self.tables = 0
        self.equations = 0
        self.out = []

    def inline(self, node):
        if isinstance(node, str):
            return re.sub(r"\s+", " ", node)
        if _skipped(node):
            return ""
        if node.tag == "math":
            return self._math(node)
        if node.tag == "br":
            return " "
        if node.has_class("ltx_ERROR"):
            self.errors += 1
        if node.has_class("ltx_note"):
            content = node.find(lambda n: n.has_class("ltx_note_content")) or node
            body = "".join(self.inline(c) for c in content.children
                           if not (isinstance(c, Node) and c.has_class("ltx_tag")))
            return f" [Footnote: {body.strip()}]"
        text = "".join(self.inline(c) for c in node.children)
        if node.tag == "img":
            return self._image(node, "")
        if not text.strip():
            return text
        if node.tag == "em" or node.has_class("ltx_emph"):
            return self._wrap(text, "*")
        if node.tag == "strong" or node.has_class("ltx_font_bold"):
            return self._wrap(text, "**")
        if node.tag in ("sup", "sub"):
            return f"<{node.tag}>{text.strip()}</{node.tag}>"
        if node.tag == "a":
            href = node.attrs.get("href", "")
            if not href or href.startswith("#") or href == text.strip():
                return text
            return f"[{text.strip()}]({urljoin(self.base_url, href)})"
        return text

    @staticmethod
    def _wrap(text, mark):
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        return f"{lead}{mark}{text.strip()}{mark}{trail}"

    def _math(self, node):
        alt = node.attrs.get("alttext", "").strip()
        if not alt:
            self.errors += 1
            return ""
        if node.attrs.get("display") == "block":
            self.equations += 1
            return f"\n\n$$\n{alt}\n$$\n\n"
        return f"${alt}$"

    def _image(self, node, caption):
        return f"![{caption}]({urljoin(self.base_url, node.attrs.get('src', ''))})"

    def _para(self, text):
        for piece in re.split(r"\n{2,}", text.strip()):
            piece = piece.strip()
            if piece.startswith("$$"):
                self.out.append(piece)
            elif piece:
                self.out.append(re.sub(r" {2,}", " ", piece))

    def block(self, node):
        if isinstance(node, str) or _skipped(node):
            return
        if node.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if not node.has_class("ltx_title_document"):
                level = 2 if node.tag == "h6" else int(node.tag[1])
                self.out.append("#" * level + " " + self.text_of(node))
        elif node.has_class("ltx_authors"):
            names = [self.text_of(n) for n in node.walk() if n.has_class("ltx_personname")]
            self.out.append("Authors: " + "; ".join(names))
        elif node.tag == "table" and node.classes & {"ltx_equation", "ltx_equationgroup", "ltx_eqn_table"}:
            self._equations(node)
        elif node.tag == "table":
            self._table(node)
        elif node.tag == "figure":
            self._figure(node)
        elif node.has_class("ltx_listing"):
            lines = [self.text_of(n) for n in node.walk() if n.has_class("ltx_listingline")]
            self.out.append("  \n".join(line for line in lines if line))
        elif node.tag == "pre":
            self.out.append("```\n" + "".join(_raw_text(node)).strip("\n") + "\n```")
        elif node.tag in ("ul", "ol"):
            for child in node.nodes():
                self._list_item(child)
        else:
            self._mixed(node)

    def _mixed(self, node):
        if not any(n.tag in BLOCK for n in node.walk()) and node.tag in BLOCK | {"root"}:
            self._para(self.inline(node))
            return
        run = []

        def flush():
            self._para("".join(run))
            run.clear()

        for child in node.children:
            if isinstance(child, str):
                run.append(self.inline(child))
            elif child.tag in BLOCK or any(n.tag in BLOCK for n in child.walk()):
                flush()
                self.block(child)
            else:
                run.append(self.inline(child))
        flush()

    def text_of(self, node):
        return re.sub(r"\s+", " ", self.inline(node)).strip()

    def _equations(self, table):
        rows = [n for n in table.walk() if n.tag == "tr"] or [table]
        for row in rows:
            maths = [n for n in row.walk() if n.tag == "math" and n.attrs.get("alttext")]
            if not maths:
                continue
            tag = row.find(lambda n: n.has_class("ltx_tag_equation"))
            body = " ".join(m.attrs["alttext"].strip() for m in maths)
            if tag:
                number = "".join(_raw_text(tag)).strip().strip("()")
                body += f" \\tag{{{number}}}"
            self.equations += 1
            self.out.append(f"$$\n{body}\n$$")

    def _table(self, table):
        self.tables += 1
        rows = []
        for tr in (n for n in table.walk() if n.tag == "tr"):
            cells = []
            for cell in tr.nodes():
                if cell.tag not in ("td", "th"):
                    continue
                span = "".join(f' {k}="{cell.attrs[k]}"' for k in ("rowspan", "colspan")
                               if cell.attrs.get(k, "1") != "1")
                cells.append(f"<{cell.tag}{span}>{self.text_of(cell)}</{cell.tag}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        self.out.append("<table>" + "".join(rows) + "</table>")

    def _figure(self, figure):
        caption_node = next((c for c in figure.nodes() if c.tag == "figcaption"), None)
        caption = self.text_of(caption_node) if caption_node else ""
        images = [n for n in figure.walk() if n.tag == "img"]
        if images and not figure.find(lambda n: n.tag == "table" or n.has_class("ltx_listing")):
            for i, image in enumerate(images):
                self.out.append(self._image(image, caption if i == 0 else ""))
            return
        if caption:
            self.out.append(caption)
        for child in figure.nodes():
            if child is not caption_node:
                self.block(child)

    def _list_item(self, item):
        tag = item.find(lambda n: n.has_class("ltx_tag_bibitem") or n.has_class("ltx_role_refnum"))
        parts = []
        for child in item.children:
            if child is tag:
                continue
            parts.append(self.inline(child))
        text = re.sub(r"\s+", " ", "".join(parts)).strip()
        prefix = f"[{self.text_of(tag)}] " if tag else ""
        self.out.append(f"- {prefix}{text}")


def _raw_text(node):
    for child in node.children:
        if isinstance(child, str):
            yield child
        else:
            yield from _raw_text(child)


def convert(html, base_url):
    """Return a Result, or raise ValueError if html is not a LaTeXML document."""
    parser = _Parser()
    parser.feed(html)
    parser.close()
    article = parser.root.find(lambda n: n.tag == "article" and n.has_class("ltx_document"))
    if article is None:
        raise ValueError("no LaTeXML document in page")
    renderer = _Renderer(base_url)
    title_node = article.find(lambda n: n.has_class("ltx_title_document"))
    title = renderer.text_of(title_node) if title_node else ""
    for child in article.nodes():
        renderer.block(child)
    return Result("\n\n".join(renderer.out) + "\n", title, renderer.errors, renderer.tables, renderer.equations)
