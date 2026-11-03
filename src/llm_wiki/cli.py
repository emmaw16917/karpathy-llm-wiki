"""Extract a paper into a raw/ Markdown file.

Implemented route: arXiv HTML. Exit codes: 0 written, 2 error,
3 no implemented route could produce the paper.
"""
import argparse
import json
import sys
import urllib.error
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import arxiv, zotero
from .arxiv_html import convert

PREPRINT_NOTE = "arXiv preprint of the Zotero item; content may differ from the published version"
NEXT_ROUTES = "Not implemented yet: arXiv LaTeX, publisher HTML, MinerU."


@dataclass
class Choice:
    paper: arxiv.Paper
    note: str


def choose_arxiv(item, lookup, search):
    """Apply the version policy: which arXiv paper may stand in for this item."""
    known = zotero.arxiv_id(item)
    if known:
        note = "" if item.item_type == "preprint" else PREPRINT_NOTE
        return Choice(lookup(known), note)
    wanted = zotero.norm_title(item.title)
    author = item.first_author.casefold()
    for paper in search(item.title):
        surnames = {name.split()[-1].casefold() for name in paper.authors if name.split()}
        if zotero.norm_title(paper.title) == wanted and author in surnames:
            return Choice(paper, PREPRINT_NOTE)
    return None


def _zotero_url(config_path):
    try:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        return config["zotero"]["local_api_url"]
    except (OSError, KeyError, ValueError):
        return zotero.DEFAULT_URL


def _render(result, item, paper, note):
    lines = [
        f"# {result.title or paper.title}", "",
        f"> Source: https://arxiv.org/abs/{paper.arxiv_id}v{paper.version}",
        f"> Collected: {date.today().isoformat()}",
        f"> Published: {(item.date if item else '') or paper.published}",
        f"> Extractor: arxiv-html (arXiv LaTeXML, v{paper.version})",
    ]
    if item:
        lines.append(f"> Zotero: {item.key}")
        if item.doi:
            lines.append(f"> DOI: {item.doi}")
    if note:
        lines.append(f"> Version-note: {note}")
    if result.errors:
        lines.append(f"> Extraction-warnings: {result.errors} conversion errors; review before compiling")
    return "\n".join(lines) + "\n\n" + result.markdown


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="llm-wiki-extract", description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--key", help="Zotero item key")
    source.add_argument("--doi", help="DOI of a Zotero item")
    source.add_argument("--title", help="exact title of a Zotero item")
    source.add_argument("--arxiv", help="arXiv id, without using Zotero")
    parser.add_argument("--out", required=True, help="output Markdown path under raw/")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args(argv)

    out = Path(args.out)
    if out.exists():
        print(f"error: {out} exists; raw files are not overwritten", file=sys.stderr)
        return 2

    try:
        item = None
        if args.arxiv:
            choice = Choice(arxiv.lookup(args.arxiv), "")
        else:
            item = zotero.find(_zotero_url(args.config), key=args.key, doi=args.doi, title=args.title)
            choice = choose_arxiv(item, arxiv.lookup, arxiv.search)
        if choice is None:
            print(f"no route: no matching arXiv version. {NEXT_ROUTES}", file=sys.stderr)
            return 3
        html, base = arxiv.fetch_html(choice.paper)
    except (LookupError, OSError, urllib.error.URLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        result = convert(html, base)
    except ValueError:
        print(f"no route: arXiv has no HTML for {choice.paper.arxiv_id}. {NEXT_ROUTES}", file=sys.stderr)
        return 3

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render(result, item, choice.paper, choice.note), encoding="utf-8", newline="\n")
    print(f"wrote {out}: {result.equations} display equations, {result.tables} tables, {result.errors} errors")
    if choice.note:
        print(f"note: {choice.note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
