"""Read pseudocode block structure from an arXiv LaTeX source package.

The package is untrusted: it is read in memory, never unpacked to disk or compiled.
"""
import gzip
import io
import posixpath
import re
import tarfile

KINDS = {
    "open": "For ForAll While If Function Procedure Loop Repeat FOR FORALL WHILE IF LOOP REPEAT",
    "middle": "ElsIf Else ELSIF ELSE",
    "line": "State Statex Return Require Ensure Input Output STATE RETURN REQUIRE ENSURE",
}
KIND_OF = {name: kind for kind, names in KINDS.items() for name in names.split()}
for _block in ("for", "while", "if", "function", "procedure", "loop"):
    KIND_OF[f"End{_block.capitalize()}"] = f"close:{_block}"
    KIND_OF[f"END{_block.upper()}"] = f"close:{_block}"
KIND_OF["Until"] = KIND_OF["UNTIL"] = "close:until"
COMMAND = re.compile(r"\\(" + "|".join(sorted(KIND_OF, key=len, reverse=True)) + r")(?![A-Za-z])")
COMMENT = re.compile(r"(?m)(?<!\\)%.*$")
ALGORITHMIC = re.compile(r"\\begin\{algorithmic\}(.*?)\\end\{algorithmic\}", re.S)
INPUT = re.compile(r"\\(?:input|include)\{([^}]+)\}")
MAX_DEPTH = 8


def read_tex_files(data):
    """Return {name: text} for .tex files in a gzipped tar or a single gzipped file."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            files = {}
            for member in archive.getmembers():
                name = posixpath.normpath(member.name)
                if member.isfile() and name.endswith(".tex") and not name.startswith(".."):
                    files[name] = archive.extractfile(member).read().decode("utf-8", "replace")
            return files
    except (tarfile.TarError, OSError, EOFError):
        pass
    try:
        return {"main.tex": gzip.decompress(data).decode("utf-8", "replace")}
    except (OSError, EOFError):
        return {}


def _expand(text, files, directory_files, depth=0):
    text = COMMENT.sub("", text)
    if depth >= MAX_DEPTH:
        return text

    def replace(match):
        name = posixpath.normpath(match.group(1))
        name = name if name.endswith(".tex") else name + ".tex"
        return _expand(files[name], files, directory_files, depth + 1) if name in files else ""

    return INPUT.sub(replace, text)


def _main_file(files):
    candidates = [name for name, text in files.items() if r"\documentclass" in COMMENT.sub("", text)]
    documents = [name for name in candidates if r"\begin{document}" in files[name]]
    return (documents or candidates or [None])[0]


def algorithm_blocks(files):
    """Return, in document order, the command kinds of each algorithmic environment."""
    main = _main_file(files)
    if main is None:
        return []
    text = _expand(files[main], files, files)
    blocks = []
    for body in ALGORITHMIC.findall(text):
        # "\State \Return x" prints one line.
        body = re.sub(r"\\(State|STATE)\s*\\(Return|RETURN)(?![A-Za-z])", r"\\State", body)
        blocks.append([KIND_OF[name] for name in COMMAND.findall(body)])
    return blocks
