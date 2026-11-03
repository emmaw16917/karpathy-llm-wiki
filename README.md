# ScholarWiki

**A paper-centered LLM wiki skill for Claude Code, Cursor, Codex, and other Agent Skills tools.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/emmaw16917/karpathy-llm-wiki?style=social)](https://github.com/emmaw16917/karpathy-llm-wiki)
[![GitHub forks](https://img.shields.io/github/forks/emmaw16917/karpathy-llm-wiki?style=social)](https://github.com/emmaw16917/karpathy-llm-wiki)
[![Agent Skills](https://img.shields.io/badge/Agent_Skills-compatible-blue)](https://agentskills.io)
[![Install](https://img.shields.io/badge/Install-npx_add--skill-green)](https://github.com/emmaw16917/karpathy-llm-wiki#install)

ScholarWiki turns papers, web pages, and notes into a durable markdown wiki that your agent maintains. Sources go into `raw/`, get compiled into evidence-grounded articles in `wiki/`, and are compared in topic overviews. Questions are answered from the wiki, with citations.

It follows [Andrej Karpathy's LLM Wiki idea](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and builds on the open-source [`karpathy-llm-wiki`](https://github.com/Astro-Han/karpathy-llm-wiki) skill (MIT). ScholarWiki's focus is different: a paper-first workflow, a stricter evidence chain, and templates designed for reading papers rather than collecting notes.

## Why ScholarWiki

- **Paper-first.** Zotero items, arXiv papers, PDFs, and web pages go through `llm-wiki-extract`, which uses arXiv HTML/LaTeX, MinerU, and Defuddle, then checks PDF extractions against the text layer.
- **Evidence-grounded.** Every number, date, and direct quote must be located in `raw/` before it is written. `scripts/check_evidence.py` re-checks the wiki; contradictions are recorded with Status blocks instead of silently rewritten.
- **Compounding, not re-searching.** New sources update existing articles, overviews, and cross-links. The wiki is the synthesis; questions cite it.
- **Paper-reading schema.** Articles ask for a mini-abstract with the headline result, a key-insight callout, prior work and the gap, a derivation chain, an optional formal core, evaluation, and missing evidence.
- **Tool-agnostic.** One `SKILL.md`, no vendor lock-in. Works with any tool that implements the Agent Skills standard.

## What Is an LLM Wiki?

An **LLM wiki** is a knowledge system where the LLM maintains structured wiki pages instead of re-searching raw documents on every question. New sources are compiled into durable markdown pages, cross-references are updated over time, and answers cite the wiki pages that already contain the synthesized knowledge.

ScholarWiki gives you four operations:

| Operation | What it does | Output |
|-----------|--------------|--------|
| **Ingest** | Extracts a source into `raw/`, triages it, then creates or updates wiki articles — or just logs it when nothing is new | New or updated wiki pages |
| **Query** | Searches the wiki and answers with citations | Grounded answers linking to markdown pages |
| **Archive** | Saves a query answer as a point-in-time wiki page | An `[Archived]` page linked from the index |
| **Lint** | Checks index integrity, links, evidence, and wiki health | Auto-fixes plus reported issues |

See [SKILL.md](SKILL.md) for the full specification.

## Quick Start

### 1. Install

```bash
npx add-skill emmaw16917/karpathy-llm-wiki
```

> **Name note:** the project is ScholarWiki; the repository and installable skill keep the `karpathy-llm-wiki` slug so existing installs and links keep working.

For the extractor, install [uv](https://docs.astral.sh/uv/), copy `config.example.json` to `config.json`, and add your MinerU token. Web pages need Node.js; Zotero items need the Zotero local API enabled.

### 2. Ingest your first source

> "Ingest this paper: https://arxiv.org/abs/1706.03762"

The skill extracts it into `raw/<topic>/<citekey>.md`, then compiles or updates the right articles in `wiki/<topic>/`.

### 3. Ask your wiki a question

> "What do I know about attention mechanisms?"

The skill searches the wiki and answers with citations linking back to your markdown pages.

### 4. Keep the wiki healthy

> "Lint my wiki"

Checks for broken links, missing index entries, evidence mismatches, stale cross-references, and related issues.

## How It Works

The core idea from Karpathy: the LLM maintains the wiki while the human focuses on choosing sources and asking good questions.

```text
your-project/
├── raw/            ← source material, changed only by logged re-extraction
│   ├── assets/citekey/
│   └── topic/
│       └── citekey.md
├── wiki/           ← compiled knowledge pages maintained by the LLM
│   ├── topic/
│   │   ├── citekey.md
│   │   ├── overview.md
│   │   └── concept-name.md
│   ├── index.md    ← global table of contents
│   └── log.md      ← append-only operation log
└── SKILL.md        ← schema layer
```

The loop is **extract → triage → compile → cascade → log**. Each new source can update multiple pages, strengthen cross-references, and record a contradiction. That is what makes the wiki compound over time.

### The evidence chain

ScholarWiki's central rule is the **grounding invariant**: a load-bearing fact in `wiki/` exists verbatim in the `raw/` files linked by that article. Compile locates every number, date, and quote before writing; lint re-checks the high-signal literals with `scripts/check_evidence.py`. If a source is replaced, `--replace` records the old file's hash, and the articles that cited it are re-checked.

### Paper workflow

- **Extraction routes:** arXiv HTML → public PDF via MinerU → Zotero PDF. Web pages and blog posts use Defuddle.
- **Verification:** PDF extractions are compared with the text layer. Low-coverage pages, numbers absent from the PDF, and unresolved table or image warnings are surfaced for review.
- **Compile:** one article per source, named by citekey. A topic gets an `overview.md` when it has a second paper. Concept pages are created only when the user asks or approves a lint suggestion.
- **Re-extraction:** `--replace` swaps a raw file only after a successful extraction, records the old hash, and flags the articles that need re-checking. Because it deletes the old raw file, keep your knowledge base in its own private git repository; do not store it in this repository.
- **Templates:** `references/paper-template.md` and `references/overview-template.md` define the article and comparison schemas; the other files in `references/` cover raw files, concepts, indexes, archives, and status blocks.

See [examples/](examples/) for sample wiki pages, source files, and operation logs.

## Install

```bash
npx add-skill emmaw16917/karpathy-llm-wiki
```

Works with any tool that supports the [Agent Skills](https://agentskills.io) standard.

## Tool Compatibility

| Tool | Install method |
|------|----------------|
| Claude Code | `npx add-skill emmaw16917/karpathy-llm-wiki` |
| Cursor | `npx add-skill emmaw16917/karpathy-llm-wiki` |
| Codex CLI | Copy to `.agents/skills/karpathy-llm-wiki/` |
| OpenCode | `npx add-skill emmaw16917/karpathy-llm-wiki` |
| Other tools | Copy `SKILL.md`, `references/`, and `scripts/` into the skill directory |

## Design Boundaries

Deliberately not built:

- **Source-hash freshness tracking** — `raw/` is immutable except for logged re-extraction; the replaced file's hash is recorded in its header and the log, without a separate freshness index.
- **Persisted line-number citations** — every observed fidelity error was "value absent from the source", which a whole-file grep catches. Anchors only disambiguate a failure mode that has not occurred, and the annotation friction makes agents skip the rule.
- **Numeric confidence or quality scores** — false precision with no calibration behind it. Evidence strength belongs in the prose.
- **Per-article review dates** — nobody can predict at compile time how fast a domain moves. Maintenance is driven by whole-wiki lint, not per-page timers.
- **Access-based decay** — frequently asked is not the same as true.
- **Retract / bad-source machinery** — has not happened yet. Handle it manually until it does.
- **Automatic hooks and scheduled runs** — those belong to the agent harness, not a tool-agnostic skill.
- **Vector or graph search** — at 50K–100K tokens of curated wiki, grep and read are more reliable. Add search tooling only when recall measurably degrades.
- **Typed relationship ontologies** — link semantics live in the prose around the link.
- **OKF conformance** — the spec is a v0.1 draft with a minimal tooling ecosystem. Tracked; will be revisited.
- **MCP servers, UIs, output subsystems** — outside the boundary of a tool-agnostic skill.

## Lineage

ScholarWiki follows [Andrej Karpathy's LLM Wiki idea](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): the LLM writes and maintains the wiki; the human reads and asks questions.

It began as a fork of [Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) (MIT). The ingest → compile → query → lint loop and the `raw/` + `wiki/` layout come from that project. ScholarWiki's paper-centered extractor, evidence checks, re-extraction flow, and templates are its own.

See also: [lucasastorian/llmwiki](https://github.com/lucasastorian/llmwiki), [atomicmemory/llm-wiki-compiler](https://github.com/atomicmemory/llm-wiki-compiler). We are tracking Google's [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) draft and will evaluate compatibility once the spec and tooling mature.

## License

[MIT](LICENSE)
