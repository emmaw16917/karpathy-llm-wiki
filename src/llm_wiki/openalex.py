"""Find a public PDF of the published version through OpenAlex."""
import json
import urllib.error
import urllib.parse
import urllib.request

from . import net


def published_pdf(work):
    locations = [work.get("best_oa_location") or {}] + (work.get("locations") or [])
    for location in locations:
        if location.get("version") == "publishedVersion" and location.get("pdf_url"):
            return location["pdf_url"]
    return None


def published_version(work):
    """Return (doi, venue) when the work has a published version other than arXiv."""
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    if not doi or doi.casefold().startswith("10.48550/arxiv."):
        return None
    for location in work.get("locations") or []:
        if location.get("version") == "publishedVersion":
            return doi, (location.get("source") or {}).get("display_name") or "unknown venue"
    return None


def find_published_version(arxiv_id):
    """Return (doi, venue) for a preprint, or None. None does not prove there is no published version."""
    url = "https://api.openalex.org/works/doi:10.48550/arXiv." + urllib.parse.quote(arxiv_id, safe="/")
    request = urllib.request.Request(url, headers={"User-Agent": "llm-wiki-extract/0.1"})
    try:
        with net.urlopen(request, timeout=30) as resp:
            return published_version(json.load(resp))
    except (OSError, ValueError):
        return None


def find_published_pdf(doi):
    """Return a published-version PDF URL, or None. Lookup failures also return None."""
    url = "https://api.openalex.org/works/doi:" + urllib.parse.quote(doi, safe="/")
    request = urllib.request.Request(url, headers={"User-Agent": "llm-wiki-extract/0.1"})
    try:
        with net.urlopen(request, timeout=30) as resp:
            return published_pdf(json.load(resp))
    except (OSError, ValueError):
        return None
