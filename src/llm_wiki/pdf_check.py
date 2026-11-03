"""Detect markup annotations stored inside a PDF, including compressed object streams."""
import re
import zlib
from pathlib import Path

MARKUP = rb"/Subtype\s*/(Highlight|Underline|StrikeOut|Squiggly|Text|FreeText|Ink|Stamp|Caret|Square|Circle|Line|Polygon|PolyLine)\b"
STREAM = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)


def embedded_annotations(path):
    """Return the set of markup annotation types found in the file."""
    data = Path(path).read_bytes()
    found = {m.decode() for m in re.findall(MARKUP, data)}
    for match in STREAM.finditer(data):
        try:
            text = zlib.decompress(match.group(1))
        except zlib.error:
            continue
        if b"/Subtype" in text:
            found |= {m.decode() for m in re.findall(MARKUP, text)}
    return found
