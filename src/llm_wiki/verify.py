"""Compare an extraction with the PDF text layer, page by page.

The text layer is not ground truth: chart labels appear only there, and
scanned PDFs have none. Results are review hints, so numbers are reported
and never rewritten.
"""
import collections
import logging
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass

LOW_COVERAGE = 0.6
MIN_PAGE_WORDS = 8
NUMBER = re.compile(r"(?<![\d.])\d+\.\d+(?!\d)|(?<![\d.])\d{5,}(?![\d.])")
LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
URL = re.compile(r"\bhttps?://\S+")
MATH = re.compile(r"\$\$.*?\$\$|\$[^$\n]*\$", re.S)


@dataclass
class Report:
    coverage: float
    low_pages: list
    extra_numbers: list
    missing_numbers: dict
    page_coverage: dict


def normalize_text(text):
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    return re.sub(r"(?<=[a-z])-\s*\n\s*(?=[a-z])", "", text)


def words(text):
    return set(re.findall(r"[a-z]{3,}", normalize_text(text).lower()))


def _numbers(text):
    text = URL.sub(" ", LINK.sub(r"\1", normalize_text(text)))
    text = MATH.sub(lambda m: re.sub(r"\s+", "", m.group(0)), text)
    text = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", text)
    return set(NUMBER.findall(text))


def edge_lines(pages):
    """Return lines repeated at page edges: running headers and footers."""
    counts = collections.Counter()
    for page in pages:
        lines = [line.strip() for line in normalize_text(page).splitlines() if line.strip()]
        counts.update(set(lines[:2] + lines[-2:]))
    needed = max(3, len(pages) // 4)
    return {line for line, count in counts.items()
            if count >= needed and 8 <= len(line) <= 120 and re.search(r"[A-Za-z]{3}", line)}


def compare(body, pages):
    md_words = words(body)
    md_numbers = _numbers(body)
    all_pdf_numbers = set()
    missing = {}
    page_coverage = {}
    low_pages = []
    found = total = 0
    running = edge_lines(pages)
    for number, page in enumerate(pages, 1):
        page = "\n".join(line for line in normalize_text(page).splitlines() if line.strip() not in running)
        page_words = words(page)
        hits = len(page_words & md_words)
        found += hits
        total += len(page_words)
        share = hits / len(page_words) if page_words else 1.0
        page_coverage[str(number)] = round(share, 3)
        if len(page_words) >= MIN_PAGE_WORDS and share < LOW_COVERAGE:
            low_pages.append(number)
        page_numbers = _numbers(page)
        all_pdf_numbers |= page_numbers
        absent = sorted(page_numbers - md_numbers)
        if absent:
            missing[str(number)] = absent
    return Report(
        found / total if total else 1.0, low_pages,
        sorted(md_numbers - all_pdf_numbers), missing, page_coverage,
    )


def read_pages(path):
    """Return each page's text, or None if the PDF has no readable text layer."""
    pages = _pdftotext_pages(path)
    if pages is None:
        pages = _pypdf_pages(path)
    return pages if pages and sum(map(len, pages)) >= 100 else None


def _pdftotext_pages(path):
    """Read pages one at a time: form feeds also occur inside pages, so they cannot delimit them."""
    if not shutil.which("pdftotext"):
        return None
    try:
        from pypdf import PdfReader

        logging.getLogger("pypdf").setLevel(logging.ERROR)
        count = len(PdfReader(str(path)).pages)
    except Exception:
        return None
    pages = []
    for number in range(1, count + 1):
        command = ["pdftotext", "-enc", "UTF-8", "-f", str(number), "-l", str(number), str(path), "-"]
        try:
            done = subprocess.run(command, capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            return None
        if done.returncode != 0:
            return None
        pages.append(done.stdout.decode("utf-8", "replace").strip("\f").replace("\f", "\n"))
    return pages


def _pypdf_pages(path):
    # pypdf raises many types on malformed files; a bad page must not void the others.
    try:
        from pypdf import PdfReader

        logging.getLogger("pypdf").setLevel(logging.ERROR)
        reader = PdfReader(str(path))
        pdf_pages = list(reader.pages)
    except Exception:
        return None
    pages = []
    for page in pdf_pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages
