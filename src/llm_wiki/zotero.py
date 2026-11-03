"""Read-only lookups through Zotero's local HTTP API."""
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_URL = "http://localhost:23119/api/users/0"
NON_BIBLIOGRAPHIC = {"note", "attachment", "annotation"}
ARXIV_ID = r"(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})"


@dataclass
class Item:
    key: str
    item_type: str
    title: str
    doi: str
    url: str
    archive_id: str
    extra: str
    date: str
    first_author: str
    citation_key: str = ""
    authors: list = field(default_factory=list)
    parsed_date: str = ""
    conference: str = ""
    proceedings: str = ""
    journal: str = ""


@dataclass
class Attachment:
    key: str
    path: Path


def norm_title(title):
    return re.sub(r"[\W_]+", "", title).casefold()


def _creator_name(creator):
    full = f"{creator.get('firstName', '')} {creator.get('lastName', '')}".strip()
    return full or creator.get("name", "")


def _item(raw):
    d = raw["data"]
    creators = d.get("creators") or [{}]
    return Item(
        d["key"], d["itemType"], d.get("title", ""), d.get("DOI", ""), d.get("url", ""),
        d.get("archiveID", ""), d.get("extra", ""), d.get("date", ""),
        creators[0].get("lastName") or creators[0].get("name", ""),
        d.get("citationKey", ""),
        [_creator_name(c) for c in creators if c.get("creatorType") == "author"],
        raw.get("meta", {}).get("parsedDate", ""),
        d.get("conferenceName", ""), d.get("proceedingsTitle", ""), d.get("publicationTitle", ""),
    )


def _get(base, path):
    req = urllib.request.Request(f"{base}/{path}", headers={"Zotero-Allowed-Request": "1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _search(base, text, qmode):
    query = urllib.parse.urlencode({"q": text, "qmode": qmode, "itemType": "-attachment", "limit": 50})
    return [_item(r) for r in _get(base, f"items?{query}") if r["data"]["itemType"] not in NON_BIBLIOGRAPHIC]


def find(base=DEFAULT_URL, key=None, doi=None, title=None):
    """Return the single matching item, or raise LookupError."""
    if key:
        return _item(_get(base, f"items/{key}"))
    if doi:
        wanted = doi.casefold()
        matches = [i for i in _search(base, doi, "everything") if i.doi.casefold() == wanted]
    else:
        wanted = norm_title(title)
        matches = [i for i in _search(base, title, "titleCreatorYear") if norm_title(i.title) == wanted]
    if len(matches) != 1:
        raise LookupError(f"expected one Zotero item, found {len(matches)}: {[m.key for m in matches]}")
    return matches[0]


def pdf_attachment(base, item_key, data_dir):
    """Return the item's PDF, preferring a copy stored by Zotero over a linked file."""
    children = [c for c in _get(base, f"items/{item_key}/children")
                if c["data"].get("itemType") == "attachment" and c["data"].get("contentType") == "application/pdf"]
    for child in children:
        data = child["data"]
        if data.get("linkMode") in ("imported_file", "imported_url") and data.get("filename"):
            return Attachment(child["key"], Path(data_dir) / "storage" / child["key"] / data["filename"])
    for child in children:
        if child["data"].get("linkMode") == "linked_file" and child["data"].get("path"):
            return Attachment(child["key"], Path(child["data"]["path"]))
    return None


def html_attachment(base, item_key, data_dir):
    """Return the item's stored web snapshot, or None."""
    for child in _get(base, f"items/{item_key}/children"):
        data = child["data"]
        if (data.get("itemType") == "attachment" and data.get("contentType") == "text/html"
                and data.get("linkMode") in ("imported_file", "imported_url") and data.get("filename")):
            return Attachment(child["key"], Path(data_dir) / "storage" / child["key"] / data["filename"])
    return None


def arxiv_id(item):
    """Return the arXiv id recorded on the item, without any version suffix."""
    patterns = [
        (item.doi, r"10\.48550/arxiv\." + ARXIV_ID),
        (item.archive_id, r"arxiv:" + ARXIV_ID),
        (item.url, r"arxiv\.org/(?:abs|pdf|html)/" + ARXIV_ID),
        (item.extra, r"arxiv:\s*" + ARXIV_ID),
    ]
    for value, pattern in patterns:
        match = re.search(pattern, value or "", re.IGNORECASE)
        if match:
            return match.group(1)
    return None
