"""Bibliographic front matter for raw files."""
import json
import re

from . import zotero

JOURNALS = {
    "proceedings of the vldb endowment": "PVLDB",
    "proceedings of the acm on management of data": "PACMMOD",
    "ieee transactions on software engineering": "TSE",
    "acm transactions on software engineering and methodology": "TOSEM",
}
APOSTROPHE = re.compile(r"^([A-Za-z][\w-]*)\s*['’]\s*(\d{2})\b")
PARENTHESIZED = re.compile(r"\(([A-Z][A-Za-z0-9-]{1,14})\)")
ISO_DATE = re.compile(r"^\d{4}(-\d{2}){0,2}$")


def published(item):
    if item.parsed_date:
        return item.parsed_date
    return item.date if ISO_DATE.match(item.date or "") else ""


def venue(item, published_date):
    """Return a short venue such as "ASE 2019"; an unknown name is kept whole."""
    year = (published_date or "")[:4]
    if item.item_type == "preprint" and zotero.arxiv_id(item):
        return f"arXiv {year}".strip()
    names = [name for name in (item.conference, item.proceedings) if name]
    for name in names:
        match = APOSTROPHE.match(name)
        if match:
            return f"{match.group(1)} 20{match.group(2)}"
    for name in names:
        found = PARENTHESIZED.findall(name)
        if found:
            return f"{found[-1]} {year}".strip()
    if item.journal:
        return f"{JOURNALS.get(item.journal.casefold(), item.journal)} {year}".strip()
    return f"{names[0]} {year}".strip() if names else ""


def front_matter(fields):
    lines = ["---"]
    for name, value in fields.items():
        if not value:
            continue
        if isinstance(value, str) and ISO_DATE.match(value):
            lines.append(f"{name}: {value}")
        else:
            lines.append(f"{name}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n"
