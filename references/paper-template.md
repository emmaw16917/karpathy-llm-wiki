---
topic: {primary problem domain}
also: [{second domain, only if the paper truly solves that problem too}]
---

# {Paper short name}: {Paper title}

> Sources: {First author et al., YYYY-MM (venue)}
> Raw: [{name}](../../raw/{topic}/{citekey}.md){; every other raw file whose facts are stated here}
> Updated: {YYYY-MM-DD}

{Two or three sentences: the problem, the approach, and the headline result with its dataset, baseline, and condition. This is the article's mini-abstract; keep it self-contained.}

> **Key insight:** {The observation or mechanism that makes the approach work, in one or two sentences and in your own words. The summary says what was done and what happened; the insight says why it can work. If the paper states no explicit insight, give the implicit rationale and mark it as your reading.}

## Problem and Challenges

{One sentence on why this problem matters. Only background particular to this paper; shared background belongs in the overview.}

**Prior work and the gap.** {The mainstream approach and where it falls short. The gap can take several forms: an assumption that breaks, a case the prior work never studied, an incomplete solution, a missing evaluation, or a capability that only recently became available. State which form this paper claims, and attribute the claim to the paper.}

**Challenges.** {The technical challenges that follow from that gap, and which of them the paper addresses.}

## Contributions and Method

{One subsection per contribution. Follow one chain: challenge → obstacle → design choice → what it is and how it works. Keep algorithm details here. These are the paper's own claims of novelty.}

{Optional, only when equations carry the contribution — otherwise delete this subsection:}
### Formal core

{The objective, estimator, or theorem; its assumptions; and what it buys. Explain why each part exists, not what each symbol denotes.}

## Evaluation

{Headline numbers first, each with its dataset and baseline. Map each claim to the experiment that tests it; do not just list results.}

- **Environment:** {hardware, threads, language}
- **Datasets:** {which, how many, total size}
- **Baselines:** {which, and whether they were re-run or copied from other papers}
- **Metrics:** {definitions}

| RQ | Result | What it shows |
|----|--------|---------------|

## Limitations and Open Doubts

{Our analysis, not the authors': weak spots, internal inconsistencies, unfair comparisons, alternative explanations the experiments do not rule out, and material evidence the claims would need but the paper does not provide. If a missing experiment would change the conclusion, name it explicitly. Mark conflicts with other sources with a Status: Disputed block.}

## See Also

- [{Topic} overview](overview.md)
