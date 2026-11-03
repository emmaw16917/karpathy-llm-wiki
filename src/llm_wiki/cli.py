"""Extract a paper into a raw/ Markdown file.

Route order: arXiv HTML, public PDF through MinerU, then the Zotero PDF
uploaded to MinerU. Exit codes: 0 written, 2 error, 3 no usable route.
"""
import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath

from . import arxiv, cleanup, mineru, net, openalex, pdf_check, quality, tables, verify, zotero
from .arxiv_html import convert

PREPRINT_NOTE = "arXiv preprint of the Zotero item; content may differ from the published version"
ARXIV_DOI_PREFIX = "10.48550/arxiv."


@dataclass
class Choice:
    paper: arxiv.Paper
    note: str


@dataclass
class Extraction:
    title: str
    body: str
    source: str
    extractor: str
    published: str = ""
    note: str = ""
    original: str = ""
    errors: int = 0
    image_tables: int = 0
    remote_images: int = 0
    table_source: str = ""
    reference: object = None
    repairs: str = ""
    verification: str = ""


class NoRoute(Exception):
    pass


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


def _load_config(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _strip_title(markdown, title):
    """Drop the paper's own title heading; the raw header already carries it."""
    wanted = zotero.norm_title(title)
    lines = markdown.strip().splitlines()
    for i, line in enumerate(lines[:40]):
        if line.startswith("# ") and zotero.norm_title(line) == wanted:
            del lines[i]
            break
    return "\n".join(lines).strip() + "\n"


def _is_doubled(body):
    ratio = quality.doubled_ratio(body)
    if ratio > quality.DOUBLED_LIMIT:
        print(f"route: rejected extraction, {ratio:.0%} of its text is repeated (bad PDF text layer)")
        return True
    return False


def _from_arxiv_html(choice):
    paper = choice.paper
    html, base = arxiv.fetch_html(paper)
    try:
        result = convert(html, base)
    except ValueError:
        print(f"route: arXiv has no HTML for {paper.arxiv_id}")
        return None
    return Extraction(
        result.title or paper.title, result.markdown,
        f"https://arxiv.org/abs/{paper.arxiv_id}v{paper.version}",
        f"arxiv-html (arXiv LaTeXML, v{paper.version})",
        paper.published, choice.note, errors=result.errors, image_tables=result.image_tables,
        reference=f"https://arxiv.org/pdf/{paper.arxiv_id}v{paper.version}",
    )


def _mineru_client(config):
    settings = config.get("mineru", {})
    token = (os.environ.get("MINERU_API_TOKEN") or settings.get("api_token") or "").strip()
    if not token:
        return None
    return mineru.Client(token, settings.get("base_url", mineru.DEFAULT_BASE), settings.get("language", "en"))


def _fill_image_tables(extraction, config):
    """Keep the HTML text, whose math is exact, and take only image tables from the PDF."""
    client = _mineru_client(config)
    if client is None:
        return
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_body = client.parse_url(extraction.reference, Path(tmp) / "images")
    except mineru.MineruError as e:
        print(f"route: could not parse image tables: {e}")
        return
    extraction.body, filled = tables.merge_tables(extraction.body, pdf_body)
    extraction.image_tables -= filled
    if filled:
        extraction.table_source = f"{filled} tables from mineru-{mineru.MODEL} on {extraction.reference}"


def _asset_dir(out):
    """Return raw/assets/<stem>, or assets/<stem> beside a file outside raw/."""
    root = next((parent for parent in out.parents if parent.name == "raw"), out.parent)
    return root / "assets" / out.stem


def _asset_link(out, assets):
    return os.path.relpath(assets, out.parent).replace("\\", "/")


def _save_image(url, path):
    request = urllib.request.Request(url, headers={"User-Agent": arxiv.USER_AGENT})
    try:
        with net.urlopen(request, timeout=120) as resp:
            data = resp.read()
    except (OSError, http.client.HTTPException):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def _localize_images(body, assets, link):
    """Point image links at local files. Return (body, images that stayed remote)."""
    failed = 0

    def rewrite(match):
        nonlocal failed
        prefix, source = match.group(1), match.group(2)
        if source.startswith("images/"):
            return f"{prefix}{link}/{source[len('images/'):]})"
        if not source.startswith(("http://", "https://")):
            return match.group(0)
        name = PurePosixPath(urllib.parse.urlsplit(source).path).name
        if not _save_image(source, assets / name):
            failed += 1
            return match.group(0)
        return f"{prefix}{link}/{name})"

    return re.sub(r"(!\[.*?\]\()([^)\s]+)\)", rewrite, body), failed


def _from_mineru(item, choice, config, args, assets):
    client = _mineru_client(config)
    if client is None:
        raise NoRoute("MinerU token is not configured")
    extractor =f"mineru-{mineru.MODEL}"
    title = item.title if item else choice.paper.title
    published = (item.date if item else "") or (choice.paper.published if choice else "")

    urls = [(args.pdf_url, "")] if args.pdf_url else []
    if choice and not choice.note:
        urls.append((f"https://arxiv.org/pdf/{choice.paper.arxiv_id}v{choice.paper.version}", ""))
    doi = item.doi if item else ""
    if doi and not doi.casefold().startswith(ARXIV_DOI_PREFIX):
        public = openalex.find_published_pdf(doi)
        if public:
            urls.append((public, ""))
    for url, note in urls:
        try:
            body = client.parse_url(url, assets)
        except mineru.MineruError as e:
            print(f"route: MinerU could not read the public PDF: {e}")
            continue
        if _is_doubled(body):
            continue
        body = _strip_title(cleanup.drop_cover(body, title), title)
        return Extraction(title, body, url, f"{extractor} (url)", published, note, reference=url)

    if not item:
        raise NoRoute("no public PDF was readable and no Zotero item was given")
    if not (doi or zotero.arxiv_id(item)) and not args.allow_upload:
        raise NoRoute("item has no DOI or arXiv id; pass --allow-upload to send its PDF to MinerU")
    zotero_settings = config.get("zotero", {})
    attachment = zotero.pdf_attachment(
        zotero_settings.get("local_api_url", zotero.DEFAULT_URL), item.key, zotero_settings.get("data_dir", ""))
    if attachment is None or not attachment.path.is_file():
        raise NoRoute("Zotero has no local PDF for this item")
    found = pdf_check.embedded_annotations(attachment.path)
    if found and not args.allow_annotated:
        raise NoRoute(f"PDF contains embedded annotations {sorted(found)}; pass --allow-annotated to upload it")
    digest = hashlib.sha256(attachment.path.read_bytes()).hexdigest()
    try:
        body = client.parse_file(attachment.path, assets)
    except mineru.MineruError as e:
        raise NoRoute(f"MinerU could not read the uploaded PDF: {e}") from None
    if _is_doubled(body):
        raise NoRoute("the Zotero PDF has a bad text layer; pass --pdf-url with a clean public copy")
    source = f"https://doi.org/{doi}" if doi else f"Zotero item {item.key}"
    body = _strip_title(cleanup.drop_cover(body, title), title)
    return Extraction(title, body, source, f"{extractor} (upload)", published,
                      choice.note if choice else "", f"Zotero attachment {attachment.key}, sha256:{digest}",
                      reference=attachment.path)


def _reference_pages(reference):
    """Return the text layer of a local path or URL, or None if unavailable."""
    if reference is None:
        return None
    if isinstance(reference, Path):
        return verify.read_pages(reference)
    request = urllib.request.Request(reference, headers={"User-Agent": arxiv.USER_AGENT})
    try:
        with net.urlopen(request, timeout=120) as resp, tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reference.pdf"
            path.write_bytes(resp.read())
            return verify.read_pages(path)
    except OSError:
        return None


def _apply_repairs(extraction, pages):
    extraction.body, urls = cleanup.fix_url_schemes(extraction.body)
    ligatures = running = 0
    if pages:
        extraction.body, running = cleanup.drop_lines(extraction.body, verify.edge_lines(pages))
        extraction.body, ligatures = cleanup.repair_ligatures(extraction.body, pages)
    if ligatures or urls or running:
        extraction.repairs = f"{ligatures} ligature words, {urls} URL schemes, {running} running lines"


def _verify(extraction, pages, check_path):
    if not pages:
        extraction.verification = "skipped (no readable PDF text layer)"
        return
    report = verify.compare(extraction.body, pages)
    low = ", ".join(map(str, report.low_pages)) or "none"
    extraction.verification = (
        f"pdf-text-layer; word coverage {report.coverage:.0%}; low-coverage pages: {low}; "
        f"numbers not in PDF: {len(report.extra_numbers)}; "
        f"PDF numbers not in text: {sum(map(len, report.missing_numbers.values()))}"
    )
    check_path.parent.mkdir(parents=True, exist_ok=True)
    check_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8", newline="\n")


def _render(extraction, item):
    lines = [
        f"# {extraction.title}", "",
        f"> Source: {extraction.source}",
        f"> Collected: {date.today().isoformat()}",
        f"> Published: {(item.date if item else '') or extraction.published or 'Unknown'}",
        f"> Extractor: {extraction.extractor}",
    ]
    if item:
        lines.append(f"> Zotero: {item.key}")
        if item.doi:
            lines.append(f"> DOI: {item.doi}")
    if extraction.original:
        lines.append(f"> Original: {extraction.original}")
    if extraction.note:
        lines.append(f"> Version-note: {extraction.note}")
    if extraction.table_source:
        lines.append(f"> Table-source: {extraction.table_source}")
    if extraction.repairs:
        lines.append(f"> Repairs: {extraction.repairs}")
    if extraction.verification:
        lines.append(f"> Verification: {extraction.verification}")
    warnings = []
    if extraction.errors:
        warnings.append(f"{extraction.errors} conversion errors; review before compiling")
    if extraction.image_tables:
        warnings.append(f"{extraction.image_tables} tables are images; their data is not in this text")
    if extraction.remote_images:
        warnings.append(f"{extraction.remote_images} images could not be saved locally")
    if warnings:
        lines.append("> Extraction-warnings: " + "; ".join(warnings))
    return "\n".join(lines) + "\n\n" + extraction.body


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
    parser.add_argument("--pdf-url", help="public PDF of the same version; tried before other PDF routes")
    parser.add_argument("--allow-upload", action="store_true", help="upload a PDF that has no DOI or arXiv id")
    parser.add_argument("--allow-annotated", action="store_true", help="upload a PDF with embedded annotations")
    args = parser.parse_args(argv)

    out = Path(args.out)
    if out.exists():
        print(f"error: {out} exists; raw files are not overwritten", file=sys.stderr)
        return 2
    config = _load_config(args.config)
    assets = _asset_dir(out)
    if assets.exists():
        print(f"error: {assets} exists; choose another file name or remove it", file=sys.stderr)
        return 2

    try:
        item = None
        if args.arxiv:
            choice = Choice(arxiv.lookup(args.arxiv), "")
        else:
            url = config.get("zotero", {}).get("local_api_url", zotero.DEFAULT_URL)
            item = zotero.find(url, key=args.key, doi=args.doi, title=args.title)
            choice = choose_arxiv(item, arxiv.lookup, arxiv.search)
        extraction = _from_arxiv_html(choice) if choice else None
        if extraction is None:
            extraction = _from_mineru(item, choice, config, args, assets)
    except NoRoute as e:
        shutil.rmtree(assets, ignore_errors=True)
        print(f"no route: {e}", file=sys.stderr)
        return 3
    except (LookupError, OSError, urllib.error.URLError) as e:
        shutil.rmtree(assets, ignore_errors=True)
        print(f"error: {e}", file=sys.stderr)
        return 2

    if extraction.image_tables:
        _fill_image_tables(extraction, config)
    extraction.body, extraction.remote_images = _localize_images(extraction.body, assets, _asset_link(out, assets))
    pages = _reference_pages(extraction.reference)
    if extraction.extractor.startswith("mineru"):
        _apply_repairs(extraction, pages)
    _verify(extraction, pages, out.with_name(out.stem + ".check.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render(extraction, item), encoding="utf-8", newline="\n")
    print(f"wrote {out}: {extraction.extractor}, {len(extraction.body)} chars, {extraction.errors} errors")
    print(f"verification: {extraction.verification}")
    if extraction.repairs:
        print(f"repairs: {extraction.repairs}")
    if extraction.note:
        print(f"note: {extraction.note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
