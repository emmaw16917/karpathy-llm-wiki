# TODO

## Extraction accuracy

- [ ] Reading order: MinerU can place text in the wrong spot. Example: a third author appears after `## 1 INTRODUCTION` in Learned Index. The text layer cannot detect this, because the words are all present.
- [ ] Lost ligatures outside the PDF vocabulary: `repair_ligatures` only restores words the PDF text layer confirms. Ambiguous spellings and PDFs that use private-use glyphs (such as `hps` in ACM files) stay unrepaired.
- [ ] Formula accuracy for the MinerU route: only papers with LaTeX source can be checked strictly; the text layer does not catch wrong subscripts.
- [ ] Image tables whose PDF caption is not directly above the table stay unfilled and are reported in `Extraction-warnings`.
- [ ] Pseudocode: other packages. LaTeX source is read for `algorithmic`, `algpseudocode`, and `algorithm2e`; custom `\SetKw` block commands are not.
- [ ] Review flagged pages visually: render pages that verification flags and check them against the Markdown.

## Routes

- [ ] arXiv LaTeX through Pandoc, for papers with source but no HTML.
- [ ] Publisher HTML.
- [ ] Better public PDF discovery: OpenAlex misses PDFs that are public, such as VLDB.
- [ ] Retry a public PDF once when MinerU reports `failed to read file`, before falling back to upload.

## Packaging

- [ ] Plugin layout, with `SKILL.md` calling `llm-wiki-extract`.
- [ ] Update `SKILL.md`: raw file header, `.check.json`, and the rule for re-extracting raw files.
- [ ] Read the MinerU privacy terms and file retention policy before batch uploads.
- [ ] Check the licenses of optional engines before release.
