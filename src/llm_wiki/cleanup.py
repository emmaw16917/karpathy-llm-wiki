"""Deterministic repairs of PDF extraction noise. Every repair is recorded in the raw header."""
import re

from .verify import normalize_text, words
from .zotero import norm_title

# Sub-sequences an extractor may leave behind when it loses a ligature glyph.
LIGATURE_REMNANTS = {
    "ffi": ("fi", "ff", "f", ""),
    "ffl": ("fl", "ff", "f", ""),
    "ff": ("f", ""),
    "fi": ("f", "i", ""),
    "fl": ("f", "l", ""),
    "ft": ("f", "t", ""),
    "tt": ("t", ""),
}
SCHEMES = {"hps": "https", "htps": "https", "ttps": "https", "hs": "https", "hp": "http", "htp": "http"}
PROTECTED = re.compile(r"(\$\$.*?\$\$|\$[^$\n]*\$|!?\[[^\]]*\]\([^)]*\)|<[^>]+>)", re.S)
WORD = re.compile(r"[A-Za-z]{3,}")


def fix_url_schemes(text):
    return re.subn(r"\b(hps|htps|ttps|hs|hp|htp)://", lambda m: SCHEMES[m.group(1)] + "://", text)


def _variants(pdf_words):
    """Map damaged spellings to PDF words, omitting spellings that fit several words."""
    candidates = {}
    for word in pdf_words:
        for ligature, remnants in LIGATURE_REMNANTS.items():
            for match in re.finditer(ligature, word):
                for remnant in remnants:
                    variant = word[:match.start()] + remnant + word[match.end():]
                    if len(variant) >= 3 and variant not in pdf_words:
                        candidates.setdefault(variant, set()).add(word)
    return {variant: next(iter(found)) for variant, found in candidates.items() if len(found) == 1}


def repair_ligatures(text, pages):
    """Restore a word only when the PDF lacks it and has exactly one ligature spelling of it."""
    variants = _variants(words("\n".join(pages)))
    count = 0

    def repair(match):
        nonlocal count
        word = match.group(0)
        fixed = variants.get(word.lower())
        if fixed is None:
            return word
        count += 1
        if word.isupper():
            return fixed.upper()
        return fixed.capitalize() if word[0].isupper() else fixed

    pieces = PROTECTED.split(text)
    for i in range(0, len(pieces), 2):
        pieces[i] = WORD.sub(repair, pieces[i])
    return "".join(pieces), count


def drop_cover(body, title):
    """Remove the ACM Digital Library cover page, which precedes the paper's own title."""
    lines = body.lstrip().splitlines()
    if not lines or not lines[0].startswith("Latest updates:"):
        return body
    wanted = norm_title(title)
    for i, line in enumerate(lines[:60]):
        if line.startswith("# ") and norm_title(line) == wanted:
            return "\n".join(lines[i:]) + "\n"
    return body


def drop_lines(body, running):
    kept = []
    count = 0
    for line in body.splitlines():
        if line.strip() and normalize_text(line).strip() in running:
            count += 1
        else:
            kept.append(line)
    return "\n".join(kept).strip() + "\n", count
