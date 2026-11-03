"""Fill tables that arXiv HTML stores as images with tables parsed from the PDF."""
import re

IMAGE_TABLE = re.compile(r"(?m)^!\[\W*table\s+([ivxlc\d]+)\b.*\]\([^)\s]*\)[ \t]*$", re.IGNORECASE)
CAPTION = re.compile(r"^\W*table\s+([ivxlc\d]+)\b", re.IGNORECASE)


def _labelled_tables(markdown):
    """Map each table label to the table that follows its caption."""
    blocks = [block.strip() for block in re.split(r"\n\s*\n", markdown) if block.strip()]
    found = {}
    for previous, block in zip(blocks, blocks[1:]):
        match = CAPTION.match(previous)
        if match and block.startswith("<table"):
            found.setdefault(match.group(1).upper(), block)
    return found


def merge_tables(html_body, pdf_body):
    """Insert each matching PDF table after its image. Return (body, tables inserted)."""
    available = _labelled_tables(pdf_body)
    count = 0

    def insert(match):
        nonlocal count
        table = available.get(match.group(1).upper())
        if table is None:
            return match.group(0)
        count += 1
        return f"{match.group(0)}\n\n{table}"

    return IMAGE_TABLE.sub(insert, html_body), count
