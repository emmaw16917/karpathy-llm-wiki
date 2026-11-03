"""Find a public PDF of the published version through OpenAlex."""
import json
import urllib.error
import urllib.parse
import urllib.request


def published_pdf(work):
    locations = [work.get("best_oa_location") or {}] + (work.get("locations") or [])
    for location in locations:
        if location.get("version") == "publishedVersion" and location.get("pdf_url"):
            return location["pdf_url"]
    return None


def find_published_pdf(doi):
    """Return a published-version PDF URL, or None. Lookup failures also return None."""
    url = "https://api.openalex.org/works/doi:" + urllib.parse.quote(doi, safe="/")
    request = urllib.request.Request(url, headers={"User-Agent": "llm-wiki-extract/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return published_pdf(json.load(resp))
    except (OSError, ValueError):
        return None
