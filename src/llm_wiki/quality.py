"""Checks that reject extractions which would poison raw/."""
import re

# PDFs with an overlaid text layer come back with each passage repeated nearby.
DOUBLED_LIMIT = 0.05
WINDOW = 24
SEARCH_SPAN = 400


def doubled_ratio(markdown):
    """Return the share of prose windows that recur shortly afterwards."""
    total = repeated = 0
    for block in re.split(r"\n\s*\n", markdown):
        block = block.strip()
        if block.startswith(("<table", "$$", "![", "#")):
            continue
        text = re.sub(r"\s+|<[^>]+>", "", block)
        for start in range(0, len(text) - WINDOW + 1, WINDOW):
            total += 1
            end = start + WINDOW
            if text.find(text[start:end], end, end + SEARCH_SPAN) >= 0:
                repeated += 1
    return repeated / total if total else 0.0
