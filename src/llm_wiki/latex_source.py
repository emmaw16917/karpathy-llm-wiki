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
ENVIRONMENT = re.compile(
    r"\\begin\{algorithm\*?\}(.*?)\\end\{algorithm\*?\}|\\begin\{algorithmic\}.*?\\end\{algorithmic\}", re.S)
ALGORITHM2E_PACKAGE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*algorithm2e")
# algorithm2e commands. Setup commands print nothing; the value is their argument count.
SETUP_2E = {
    "caption": 1, "label": 1, "SetKwFunction": 2, "SetKwProg": 4, "SetKw": 2, "SetKwInput": 2, "SetKwInOut": 2,
    "SetKwData": 2, "SetAlgoLined": 0, "SetAlgoNoLine": 0, "SetAlgoNoEnd": 0, "SetAlgoVlined": 0,
    "DontPrintSemicolon": 0, "LinesNumbered": 0, "LinesNotNumbered": 0, "RestyleAlgo": 1, "centering": 0,
    "small": 0, "footnotesize": 0, "scriptsize": 0, "normalsize": 0, "SetNlSty": 3, "SetAlFnt": 1, "SetAlCapFnt": 1,
    "SetKwRepeat": 3, "SetKwIF": 8, "SetKwFor": 4,
}
LINE_2E = {
    "KwIn": 1, "KwOut": 1, "KwData": 1, "KwResult": 1, "KwRequire": 1, "KwEnsure": 1, "KwRet": 1, "Return": 1,
    "tcc": 1, "tcp": 1, "lIf": 2, "lFor": 2, "lForEach": 2, "lForAll": 2, "lWhile": 2, "lElse": 1, "lElseIf": 2,
    "luIf": 2, "luElseIf": 2, "luElse": 1,
}
# The value is the block its end line closes, or "" when a later command closes it.
OPEN_2E = {
    "If": "if", "uIf": "", "For": "for", "ForEach": "for", "ForAll": "for", "While": "while",
    "Fn": "function", "Proc": "procedure",
}
# The value is (argument count, whether this command also ends the conditional).
MIDDLE_2E = {"Else": (1, True), "uElse": (1, True), "ElseIf": (2, True), "uElseIf": (2, False)}


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
    uses_2e = ALGORITHM2E_PACKAGE.search(text) is not None
    blocks = []
    for match in ENVIRONMENT.finditer(text):
        inner = ALGORITHMIC.search(match.group(0))
        if inner:
            # "\State \Return x" prints one line.
            body = re.sub(r"\\(State|STATE)\s*\\(Return|RETURN)(?![A-Za-z])", r"\\State", inner.group(1))
            blocks.append([KIND_OF[name] for name in COMMAND.findall(body)])
        elif uses_2e:
            blocks.append(_algorithm2e_tokens(match.group(1) or ""))
    return blocks


def _read_group(text, start):
    """Return (content, end) of the brace group at start, or raise ValueError."""
    depth = 0
    i = start
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    raise ValueError("unbalanced braces")


def _read_args(text, position, count):
    args = []
    for _ in range(count):
        while position < len(text) and text[position].isspace():
            position += 1
        if position >= len(text) or text[position] != "{":
            raise ValueError("missing argument")
        content, position = _read_group(text, position)
        args.append(content)
    return args, position


def _parse_2e(text):
    """Return tokens for algorithm2e content: each statement or block line prints one line."""
    tokens = []
    in_statement = False
    i = 0

    def end_statement():
        nonlocal in_statement
        if in_statement:
            tokens.append("line")
            in_statement = False

    while i < len(text):
        char = text[i]
        if char == "%":
            i = text.find("\n", i) + 1 or len(text)
            continue
        if char == "{":
            _, i = _read_group(text, i)
            in_statement = True
            continue
        if char == "\\":
            match = re.compile(r"\\([A-Za-z]+)").match(text, i)
            if not match:
                if text.startswith(("\\;", "\\\\"), i):
                    end_statement()
                elif not text.startswith("\\,", i):
                    in_statement = True
                i += 2
                continue
            name = match.group(1)
            i = match.end()
            if name in SETUP_2E:
                _, i = _read_args(text, i, SETUP_2E[name])
            elif name in LINE_2E:
                end_statement()
                _, i = _read_args(text, i, LINE_2E[name])
                tokens.append("line")
            elif name in OPEN_2E:
                end_statement()
                (_, body), i = _read_args(text, i, 2)
                tokens.append("open")
                tokens += _parse_2e(body)
                if OPEN_2E[name]:
                    tokens.append(f"close:{OPEN_2E[name]}")
            elif name in MIDDLE_2E:
                end_statement()
                args, i = _read_args(text, i, MIDDLE_2E[name][0])
                tokens.append("middle")
                tokens += _parse_2e(args[-1])
                if MIDDLE_2E[name][1]:
                    tokens.append("close:if")
            elif name == "eIf":
                end_statement()
                (_, first, second), i = _read_args(text, i, 3)
                tokens += ["open", *_parse_2e(first), "middle", *_parse_2e(second), "close:if"]
            elif name == "Repeat":
                end_statement()
                (_, body), i = _read_args(text, i, 2)
                tokens += ["open", *_parse_2e(body), "close:until"]
            else:
                in_statement = True
            continue
        if not char.isspace():
            in_statement = True
        i += 1
    end_statement()
    return tokens


def _algorithm2e_tokens(body):
    try:
        return _parse_2e(re.sub(r"^\s*\[[^\]]*\]", "", body))
    except ValueError:
        return []
