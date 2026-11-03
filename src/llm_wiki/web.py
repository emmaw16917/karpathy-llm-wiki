"""Extract web pages and Zotero snapshots to Markdown with the Defuddle CLI.

Defuddle only ever receives a path to a temporary copy. On Windows npx runs
through cmd.exe, where characters such as & in a URL would be interpreted.
"""
import http.client
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import net

DEFUDDLE = "defuddle@0.19.6"
INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁯﻿]")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
IMAGE = re.compile(r"(!\[.*?\]\()([^)\s]+)\)")
USER_AGENT = "Mozilla/5.0 (compatible; llm-wiki-extract/0.1)"


class WebError(Exception):
    pass


@dataclass
class Page:
    title: str
    author: str
    published: str
    site: str
    markdown: str


def clean_title(title):
    return INVISIBLE.sub("", title or "").strip()


def _date(value):
    match = DATE.match(str(value or "").strip())
    return match.group(0) if match else ""


def _find_date(parsed):
    found = _date(parsed.get("published"))
    if found:
        return found
    for tag in parsed.get("metaTags") or []:
        if "published" in str(tag.get("property") or tag.get("name") or "").lower():
            found = _date(tag.get("content"))
            if found:
                return found
    schema = parsed.get("schemaOrgData") or []
    for entry in schema if isinstance(schema, list) else [schema]:
        if isinstance(entry, dict) and _date(entry.get("datePublished")):
            return _date(entry["datePublished"])
    return ""


def to_page(parsed, base_url):
    def absolute(match):
        source = match.group(2)
        if source.startswith("data:"):
            return match.group(0)
        return f"{match.group(1)}{urllib.parse.urljoin(base_url, source)})"

    return Page(
        clean_title(parsed.get("title")), (parsed.get("author") or "").strip(), _find_date(parsed),
        (parsed.get("site") or parsed.get("domain") or "").strip(),
        IMAGE.sub(absolute, parsed.get("contentMarkdown") or parsed.get("content") or ""),
    )


def run_defuddle(path):
    """Return Defuddle's JSON for a local HTML file."""
    npx = shutil.which("npx")
    if not npx:
        raise WebError("web extraction needs Node.js (npx was not found)")
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "out.json"
        try:
            subprocess.run([npx, "-y", DEFUDDLE, "parse", str(path), "--json", "--md", "-o", str(output)],
                           capture_output=True, timeout=180, check=True)
            return json.loads(output.read_text(encoding="utf-8"))
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            raise WebError(f"Defuddle failed: {type(e).__name__}") from None


def _parse_bytes(data, base_url):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "page.html"
        path.write_bytes(data)
        page = to_page(run_defuddle(path), base_url)
    if not page.markdown.strip():
        raise WebError("no article content found")
    return page


def from_file(path, base_url):
    return _parse_bytes(Path(path).read_bytes(), base_url)


def from_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with net.urlopen(request, timeout=60) as resp:
            data = resp.read()
    except (OSError, http.client.HTTPException) as e:
        raise WebError(f"could not download the page: {type(e).__name__}") from None
    return _parse_bytes(data, url)
