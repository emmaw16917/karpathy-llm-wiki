"""arXiv metadata lookup and HTML download."""
import http.client
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from . import net

API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "llm-wiki-extract/0.1"


@dataclass
class Paper:
    arxiv_id: str
    version: int
    title: str
    authors: list
    published: str


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return net.urlopen(req, timeout=60)


def _parse_feed(data):
    papers = []
    for entry in ET.fromstring(data).findall(f"{ATOM}entry"):
        match = re.search(r"/abs/(.+?)v(\d+)$", entry.findtext(f"{ATOM}id", ""))
        if not match:
            continue
        papers.append(Paper(
            match.group(1),
            int(match.group(2)),
            " ".join(entry.findtext(f"{ATOM}title", "").split()),
            [a.findtext(f"{ATOM}name", "") for a in entry.findall(f"{ATOM}author")],
            entry.findtext(f"{ATOM}published", "")[:10],
        ))
    return papers


def lookup(arxiv_id):
    with _get(f"{API}?id_list={urllib.parse.quote(arxiv_id)}") as resp:
        papers = _parse_feed(resp.read())
    if not papers:
        raise LookupError(f"arXiv has no paper {arxiv_id}")
    return papers[0]


def search(title):
    words = re.sub(r"[^\w\s]", " ", title).split()
    query = urllib.parse.quote('ti:"' + " ".join(words) + '"')
    with _get(f"{API}?search_query={query}&max_results=5") as resp:
        return _parse_feed(resp.read())


def fetch_source(paper):
    """Return the LaTeX source package, or None if it cannot be downloaded."""
    try:
        with _get(f"https://arxiv.org/e-print/{paper.arxiv_id}v{paper.version}") as resp:
            return resp.read()
    except (OSError, http.client.HTTPException):
        return None


def fetch_html(paper):
    """Return (html, base_url); html is empty when arXiv has no HTML version."""
    # No trailing slash: arXiv image paths already start with "<id>v<n>/".
    base = f"https://arxiv.org/html/{paper.arxiv_id}v{paper.version}"
    try:
        with _get(base) as resp:
            return resp.read().decode("utf-8", "replace"), base
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "", base
        raise
