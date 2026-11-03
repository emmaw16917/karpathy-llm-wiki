---
name: karpathy-llm-wiki
description: "Use when building or maintaining a personal LLM-powered knowledge base. Triggers: ingesting papers, Zotero items, blog posts, or other sources into a wiki, querying wiki knowledge, linting wiki quality, 'add to wiki', 'what do I know about', or any mention of 'LLM wiki' or 'Karpathy wiki'."
---

# Karpathy LLM Wiki

Build and maintain a personal knowledge base using LLMs. You manage two directories: `raw/` (immutable source material) and `wiki/` (compiled knowledge articles). Sources go into raw/, you compile them into wiki articles, and the wiki compounds over time.

Core ideas from Karpathy:
- "The LLM writes and maintains the wiki; the human reads and asks questions."
- "The wiki is a persistent, compounding artifact."

## Architecture

Three layers, all under the user's project root:

**raw/** — Immutable source material. You read, never edit by hand. The only permitted change is a logged re-extraction (see Re-extracting a raw file). Organized by topic subdirectories (e.g., `raw/machine-learning/`). Images live in `raw/assets/<raw-file-stem>/`; `assets` is not a topic.

**wiki/** — Compiled knowledge articles. You have full ownership. Organized by topic subdirectories, one level only: `wiki/<topic>/<article>.md`. Each topic holds source articles named by citekey, an `overview.md`, and optional `concept-<name>.md` pages. Contains two special files:
- `wiki/index.md` — Global index. One row per article, grouped by topic, with link + summary + Updated date.
- `wiki/log.md` — Append-only operation log.

**SKILL.md** (this file) — Schema layer. Defines structure and workflow rules.

Templates live in `references/` relative to this file. Read them when you need the exact format for raw files, source articles, overviews, concept pages, archive pages, the index, or conflict annotations.

### Initialization

Triggers only on the first Ingest. Check whether `raw/` and `wiki/` exist. Create only what is missing; never overwrite existing files:

- `raw/` directory (with `.gitkeep`)
- `wiki/` directory (with `.gitkeep`)
- `wiki/index.md` — heading `# Knowledge Base Index`, empty body
- `wiki/log.md` — heading `# Wiki Log`, empty body

If Query or Lint cannot find the wiki structure, tell the user: "Run an ingest first to initialize the wiki." Do not auto-create.

## The Grounding Invariant

Every load-bearing fact in wiki/ — numbers, dates, direct quotes — exists verbatim in the raw/ files linked by that article's Raw field. Compile *establishes* this invariant (locate before you write); lint *verifies* it (`scripts/check_evidence.py` greps the high-signal literals — suffixed or large numbers, decimals, ISO dates, longer quotes — in the linked raws; the compile-time locate-before-write rule covers the rest). Because raw/ changes only through a logged re-extraction, a verified article stays verified until then; the script re-checks the whole wiki in seconds, so there is no incremental state to maintain.

---

## Ingest

Fetch a source into raw/, then compile it into wiki/ — unless the source adds nothing new. Always fetch; whether to compile depends on the triage below.

### Fetch (raw/)

1. Pick the topic: the problem domain the source addresses (see Papers and topics). Check existing `raw/` subdirectories first, ignoring `assets`. Create a new one only for a genuinely distinct problem domain.

2. Run the extractor for papers and web pages (see Extracting sources). It names the file `raw/<topic>/<citekey>.md`.

3. For anything the extractor cannot reach, such as pasted text or a local document, ask the user for the content or use your file tools. Save it as `raw/<topic>/<citekey>.md` with the same front matter, built as the extractor does: surname, first three title words, year. Preserve original text. Clean formatting noise. Do not rewrite opinions. See `references/raw-template.md`.

### Extracting sources

Use the extractor for any paper or web page. It writes the raw file, its header, and its images, so do not write or edit them yourself:

```
uv run --project <skill-dir> llm-wiki-extract --key <zotero-key> --out raw/<topic> --config <skill-dir>/config.json
```

Instead of `--key`, you can pass `--doi`, `--title`, `--arxiv <id>`, or `--url <page>`. Zotero must be running with its local API enabled, unless you use `--arxiv` or `--url`.

The file is named `<citekey>.md`. Its YAML front matter holds `citekey`, `zotero_key`, `title`, `authors`, `published` (the publication date), `venue`, and, where they apply, `doi`, `arxiv`, and `url`. If `venue` is not a short name such as `ASE 2019`, pass `--venue "<name year>"`. Pass `--name <key>` to replace a poor citekey. Front matter is not evidence: `scripts/check_evidence.py` ignores it, so a fact stated only there cannot ground an article.

Web pages and Zotero `webpage`, `blogPost`, and `forumPost` items use Defuddle, which needs Node.js. A stored Zotero snapshot is preferred over the live page. If Zotero's citekey is poor, such as `zotero-29`, the extractor builds one from the author, title, and year. Web pages have no PDF, so they get no Verification field.

For papers, the extractor tries these routes in order and records the one it used in the Extractor field:

1. arXiv HTML. A published item may use its arXiv version when the title and first author match; the header then carries a Version-note.
2. A public PDF of the published version through MinerU. Pass `--pdf-url` to name a clean copy.
3. The Zotero PDF uploaded to MinerU.

Upload sends the user's file to an outside service. These flags override a refusal, so pass them only when the user has approved that upload:

- `--allow-upload` — the item has no DOI or arXiv id.
- `--allow-annotated` — the PDF contains embedded annotations.

Exit codes: 0 written, 2 error, 3 no usable route. On 3, tell the user the printed reason. Do not substitute a manual extraction without asking, because a PDF rejected for a bad text layer would reintroduce the same damage.

After extracting, read these header fields before compiling:

- **Verification** — compares the text with the PDF text layer. Page numbers and values are in `<file>.check.json` beside the raw file. Treat results as review hints: chart labels exist only in the PDF, and the check cannot see wrong subscripts or misplaced text.
  - `low-coverage pages` — content may be missing, or may be inside an image. Look at those pages.
  - `numbers not in PDF` — possible misreads. Check each one before relying on it.
  - `PDF numbers not in text` — a large count can mean a lost table.
- **Extraction-warnings** — unresolved problems, such as tables that remain images. Do not state facts from a table whose data is not in the text.
- **Version-note** — the text is a preprint. Say so in the article's Sources field when a load-bearing fact comes from it.
- **Table-source** — these tables came from MinerU, while the rest of the text came from arXiv HTML.
- **Published-version** — OpenAlex links this preprint to a published version. The text stays from arXiv, because its HTML and LaTeX extract better and the published PDF may need access rights. Tell the user, who may want to update the Zotero item. Its absence does not prove that no published version exists.
- **Pseudocode** — indentation comes from the LaTeX source or, when no source block aligns, is rebuilt from keywords. Check the original before relying on keyword-based block structure. Pseudocode sits in code blocks, which `scripts/check_evidence.py` skips, so a number quoted from it shows up as a suspect.

Report flagged items to the user. Never correct numbers in raw/ by hand.

### Re-extracting a raw file

Use this only when a raw file is wrong, for example after verification finds a lost table, or the user supplies a better PDF:

```
uv run --project <skill-dir> llm-wiki-extract --key <zotero-key> --out raw/<topic>/<file>.md --config <skill-dir>/config.json --replace --reason "<why>"
```

On success, the old raw file and its images are deleted and the new header records the old file's hash in the Replaces field. If extraction fails, the old version stays untouched.

Then:

1. Find the articles whose Raw field links to this file.
2. Run `scripts/check_evidence.py` on those articles. Each suspect may be a fact that changed, so check it against the new raw file and update the article. Mark a corrected claim with a Status block rather than rewriting it silently.
3. Append to `wiki/log.md`:

```
## [YYYY-MM-DD] re-extract | <project-root-relative raw file path>
- Reason: <why>
- Replaced: <sha256 from the Replaces field>
- Articles checked: <article titles, or none>
```

### Triage

After saving the raw file and before editing wiki/, search wiki/ with the source's key entities and synonyms, then state the disposition:

- **New** — creates one or more new articles.
- **Update** — merges into existing article(s).
- **Disputed** — contradicts existing content; may combine with New or Update (see Compile for conflict annotation).
- **No material** — only a duplicate version of a source the wiki already has. Keep the raw file, log it (see Post-Ingest), and stop. A source the user chose always gets its own article, even if it adds little.

New, Update, and Disputed may be combined. No material is exclusive.

### Compile (wiki/)

Every source gets one article at `wiki/<topic>/<citekey>.md`. Sources are never merged into one another; shared knowledge goes in the overview and concept pages (see Papers and topics). In all cases, check for factual conflicts: if the new source contradicts existing content, mark the contested claims with a **Status: Disputed** block (see `references/status-blocks.md`). When the conflicting content lives in separate articles, mark both and cross-link them.

**Source fidelity.** Every number, date, and direct quote must be located in the raw file (grep or read) *before* it is written; write the value exactly as found — if the source says 42K, write 42K, not 42,000. Derived values (sums, deltas, counts you computed) must show their components so each component is findable in raw. If you cannot locate a value, do not write its exact form; drop it or state it without precision.

**Which raw files to link.** The Raw field lists every raw file holding a fact the article states, including facts inside Status blocks. Sources need not be in the library:

- Another source is in raw/, and the fact comes from it → add it to Raw.
- The other source is not in raw/, but the current source describes it → link only the current source, and attribute the claim: "According to Denum, LogReducer introduced the elastic encoder". This verifies what Denum says, not what LogReducer did.
- No raw file holds the fact → do not state it. You may suggest ingesting that source.

#### Papers and topics

Write wiki articles in English, staying close to the source's own wording.

**Topics.** A topic is a problem domain: the problem a paper solves, not the method it uses. A paper applying learned indexes to log compression belongs to `log-compression`. Do not add subtopics by default; group approaches as sections inside the overview. If one direction outgrows its overview, ask the user before splitting it.

**Choosing a topic.** Each paper has exactly one primary topic, chosen by its core contribution and main evaluation metric. If that is unclear, ask the user. Record a second domain in `also` only when the paper truly solves that problem too; that domain's overview then gets a short section linking to the article, without repeating it. Do not mention a paper in a method domain's overview unless it advances that method.

**Source articles.** Follow `references/paper-template.md` for papers and technical blog posts alike, at `wiki/<topic>/<citekey>.md`. A blog post keeps the same sections, with its main approach or argument as the method. Its Evaluation lists only the evidence it gives, or states `No systematic evaluation reported`. Keep each source's specifics here: its method, its experiments, and its results. Keep your own analysis in Limitations and Open Doubts, separate from the authors' claims.

**Topic overviews.** Follow `references/overview-template.md`, at `wiki/<topic>/overview.md`. Create one when a topic gets its second paper, and update it with each later paper. Place content with this test: if a new paper could change a statement, it belongs in the overview; otherwise it belongs in the paper article.

Overviews compare methods and evaluation design only. Do not put experimental results in an overview, and never rank methods across papers: datasets, versions, kernels, and environments differ. Link to the articles for numbers.

**Concept pages.** A technique that recurs across articles, such as an encoding, can get a page at `wiki/<topic>/concept-<name>.md`, under the problem domain that uses it most. Follow `references/concept-template.md`. Overviews compare methods; concept pages explain one technique. Create one only when the user asks, or approves a Lint suggestion.

Source, overview, and concept articles share the same header fields. Key points:
- Sources field: author, organization, or publication name + date, semicolon-separated.
- Raw field: markdown links to raw/ files, semicolon-separated.
- Relative paths from `wiki/<topic>/` use `../../raw/<topic>/<file>.md` (two levels up to project root).

### Cascade Updates

After the primary article, check for ripple effects. Do not rely on the index alone: search the full wiki for the source's key entities, aliases, and the claims it touches, then update every non-archive article whose content is materially affected. Each updated file gets its Updated date refreshed.

When the new source supersedes or contradicts an existing claim, keep the old claim for the record but mark it with a Status block (see `references/status-blocks.md`): **Outdated** when something newer replaces it, **Disputed** when sources disagree. Never silently rewrite history.

Archive pages are never cascade-updated (they are point-in-time snapshots).

### Post-Ingest

Update `wiki/index.md`: add or update entries for every touched article. When adding a new topic section, include a one-line description. The Updated date reflects when the article's knowledge content last changed, not the file system timestamp. See `references/index-template.md` for format.

Append to `wiki/log.md`:

```
## [YYYY-MM-DD] ingest | <primary article title>
- Disposition: <New; Update; Disputed>
- Raw: <raw file path>
- Updated: <cascade-updated article title>
```

Omit `- Updated:` lines when no cascade updates occur. For No material, log and stop. Use a project-root-relative raw path (for example, `raw/topic/file.md`):

```
## [YYYY-MM-DD] ingest | no material: <project-root-relative raw file path>
- Disposition: No material
```

The exact no-material heading is the machine-readable inventory key; the Disposition line remains required for a complete human-readable log entry.

### Research (multi-source ingest)

Use only when the user explicitly asks to research a topic or gather sources into the wiki. Ordinary knowledge questions go to Query, which never writes files.

1. Split the topic into a few angles. For each, search with a wide net — official names, abbreviations, and synonyms, not just the literal keywords.
2. For any core claim you expect to conclude, deliberately search the opposing side: failures, criticism, failed replications.
3. Save selected sources to raw/ as usual. Searching may run in parallel; compilation must not — compile one source at a time, because index.md, log.md, and cascade updates are shared state.

---

## Query

Search the wiki and answer questions. Examples of triggers:
- "What do I know about X?"
- "Summarize everything related to Y"
- "Compare A and B based on my wiki"

### Steps

1. Read `wiki/index.md` to locate candidate articles, then full-text search wiki/ with the topic's key terms *and their synonyms*. Never claim the wiki has no relevant content until both the index and the full-text search come back empty — and say that you searched.
2. Read the articles you found and synthesize an answer.
3. Prefer wiki content over your own training knowledge. Cite sources with markdown links: `[Article Title](wiki/topic/article.md)` (project-root-relative paths for in-conversation citations; within wiki/ files, use paths relative to the current file).
4. Output the answer in the conversation. Do not write files unless asked.

### Archiving

When the user explicitly asks to archive or save the answer to the wiki:

1. Write the answer as a new wiki page. See `references/archive-template.md`. When converting conversation citations to the archive page, rewrite project-root-relative paths (e.g., `wiki/topic/article.md`) to file-relative paths (e.g., `../topic/article.md` or `article.md` for same-directory).
   - Sources: markdown links to the wiki articles cited in the answer.
   - No Raw field (content does not come from raw/).
   - File name reflects the query topic, e.g., `transformer-architectures-overview.md`.
   - Place in the most relevant topic directory.
2. Always create a new page. Never merge into existing articles (archive content is a synthesized answer, not raw material).
3. Update `wiki/index.md`. Prefix the Summary with `[Archived]`.
4. Append to `wiki/log.md`:
   ```
   ## [YYYY-MM-DD] query | Archived: <page title>
   ```

---

## Lint

Quality checks on the wiki. Three categories with different authority levels.

### Safe Fixes (auto-fix)

Fix these automatically:

**Index consistency** — compare `wiki/index.md` against actual wiki/ files (excluding index.md and log.md):
- File exists but missing from index → add entry with `(no summary)` placeholder. For Updated, use the article's metadata Updated date if present (for archive pages, the Archived date); otherwise fall back to file's last modified date.
- Index entry points to nonexistent file → mark as `[MISSING]` in the index. Do not delete the entry; let the user decide.
- Index entry's Updated differs from the article's metadata Updated (or Archived, for archive pages) → update the index entry to match the article.

**Internal links** — for every markdown link in wiki/ article files (body text and Sources metadata), excluding Raw field links (validated by Raw references below), excluding See Also section links (handled by the See Also rule below), and excluding index.md/log.md (handled above):
- Target does not exist → search wiki/ for a file with the same name elsewhere.
  - Exactly one match → fix the path.
  - Zero or multiple matches → report to the user.

**Raw references** — every link in a Raw field must point to an existing raw/ file:
- Target does not exist → search raw/ for a file with the same name elsewhere.
  - Exactly one match → fix the path.
  - Zero or multiple matches → report to the user.

**See Also** — within each topic directory:
- Target of a See Also link does not exist → search wiki/ for a file with the same name elsewhere.
  - Exactly one match → fix the path.
  - Zero matches → remove the link (a dead cross-reference is not load-bearing).
  - Multiple matches → report to the user.

### Mechanical Reports (no fixes)

Run these mechanically with `python3 <skill-dir>/scripts/check_evidence.py <project-root>` (on Windows, use `python` or `py -3`; requires Python 3.10+; optionally followed by project-root-relative article paths to limit scope). Default scope is the whole wiki; the script is fast. Report findings; never auto-fix facts.

**Source fidelity** — reported suspects are candidates, not verdicts: derived values and product names may appear. Judge each against the raw context and report only real mismatches.

**Evidence errors** — articles the script cannot verify (missing Raw field, unresolvable Raw links, or Raw links escaping `raw/`). These always need a decision, not a fix from the script.

**Unreferenced raw files** — files logged with a No material disposition are excluded; everything else is a genuine backlog reminder.

### Judgment Reports (no fixes)

These rely on your judgment. Report findings without auto-fixing:

- Factual contradictions across articles
- Outdated claims superseded by newer sources but still presented without a Status block
- Missing conflict annotations where sources disagree
- Obviously missing cross-references between related articles (suggest them; do not add silently)
- Malformed Status blocks (Outdated missing its date, or either block missing its explanation; format reference: `references/status-blocks.md`)
- Orphan pages with no inbound links from other wiki articles
- Missing cross-topic references
- Concepts mentioned in three or more source articles without a concept page (suggest them; create one only if the user approves)
- Archive pages whose cited source articles have been substantially updated since archival

### Post-Lint

Append to `wiki/log.md`:

```
## [YYYY-MM-DD] lint | <N> issues found, <M> auto-fixed
```

---

## Conventions

- Standard markdown with relative links throughout.
- wiki/ supports one level of topic subdirectories only. No deeper nesting.
- Today's date for log entries, Collected dates, and Archived dates. Updated dates reflect when the article's knowledge content last changed. Published dates come from the source (use `Unknown` when unavailable).
- Inside wiki/ files, all markdown links use paths relative to the current file. In conversation output, use project-root-relative paths (e.g., `wiki/topic/article.md`).
- Ingest updates both `wiki/index.md` and `wiki/log.md` (a No material ingest updates only the log). Re-extraction updates `wiki/log.md`. Archive (from Query) updates both. Lint updates `wiki/log.md` (and `wiki/index.md` only when auto-fixing index entries). Plain queries do not write any files.
