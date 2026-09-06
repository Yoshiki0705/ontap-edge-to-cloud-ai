# Reference-Doc / Guide Quality Bar

> Read when writing or revising a technical reference or guide. Does not apply to
> conversation or short answers.
>
> 日本語: [reference-doc-quality.md](reference-doc-quality.md)

## Required elements

| Element | Purpose |
|---|---|
| Conclusion in the executive summary | the reader can decide within the first ten lines |
| FAQ / common misconceptions | recovers the assumptions nobody read |
| Selection flowchart (mermaid is fine) | separates "which one" from the prose |
| OT/IT security considerations (where applicable) | mandatory for docs touching plant or field equipment |
| Phased adoption steps | the order from PoC to production |
| Related Documents (back-links) | reachability; an unlinked doc is an unread doc |

## JA/EN parity

`docs/ja/` and `docs/en/` keep the same `## ` heading structure and count. A
change to one lands in both in the same commit.
`.github/workflows/agent-output-audit.yml` warns on a heading-count difference.

## Japanese headings are noun phrases

A Japanese section heading at `##` or below is a noun phrase. A heading sits where
the reader scans for a label; a verb-final, interrogative or predicative heading
puts a sentence there, so deciding whether the section is the right one takes
parsing first.

| Avoid | Use |
|---|---|
| 自分の環境で確かめる | 自環境での確認手順 |
| なぜこの区分が必要か | この区分が必要な理由 |
| 記録されない読み取りがあります | 記録されない読み取りの存在 |

**Nominalising must not drop the assertion.** A heading often carries the finding
itself. Keep it with a suffix (〜の存在 / 不在 / 成立 / 不成立 / 無効化 / 差 /
上限 / 理由) or a modifier (未対応の〜 / 既定で無効な〜 / 一方向に保つ〜). A
heading no suffix can hold is carrying a sentence; move it into the prose.

Out of scope: H1 (the document title in this repository, which is a one-line
claim), English headings, `#` lines inside code fences, table cells and list
items. A heading that cannot serve as an index entry — a timeline entry, advice
whose imperative tone is the content, a stated intention — breaks when
nominalised; mark the heading line `<!-- allow:heading-style -->` and say in the
surrounding prose why it is narrative.

Renaming changes the anchor. Find the referrers with
`grep -rn '](#<old slug>' --include='*.md' .` and fix them in the same commit.
GitHub serves an unknown fragment as the top of the page, so the referring side
cannot tell it broke.

```bash
make headings   # detector self-test, then the whole *.md tree
```

## Naming

- First mention **Amazon FSx for NetApp ONTAP**, then **FSx for ONTAP**
- Access points are **FSx for ONTAP S3 AP**
- Never `FSxN`, bare `FSx`, or `FSx ONTAP`
- The only exception is a verbatim external citation title; mark that line `allow:naming`

## Writing comparisons

Present options, not rankings. State trade-offs symmetrically, including the
recommended option's own constraints. `最強`, `game-changer`, `競合ツール`,
`優位性`, `より優れ`, `is better than`, `is superior to` are hard-failed by
`agent-output-audit.yml`.

## Never publish

Personal or persona names, email addresses, AWS account IDs, internal IPs and
hostnames, support case numbers, vendor-internal ticket IDs. Use role-based
references (`Storage Specialist lens`) and "an internal product request
(tracked)".

Keep review-process metadata out of published docs (round counts, review dates,
lens counts). It is noise for readers; provenance belongs in `.private/`
(gitignored).

## Numbers and confidence

- Publish a performance or cost number with its environment (version, region,
  configuration, measurement date)
- Separate "sample run" from "production estimate"
- Write "not verified" where that is the case, rather than filling in a plausible
  default

## Before committing

```bash
make secrets
# CI mirrors these checks: .github/workflows/agent-output-audit.yml
```

## Related documents

- [Quality gates](quality-gates_en.md)
- [Supply-chain security](supply-chain-security_en.md)
