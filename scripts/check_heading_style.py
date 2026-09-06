#!/usr/bin/env python3
"""Fail when a Japanese section heading is a sentence rather than a noun phrase.

Why this exists
---------------
A heading occupies the position a reader scans for a label. A verb-final,
interrogative or predicative heading puts a sentence there instead, so the reader
has to parse it before knowing whether the section is the one they want. The rule
is written up in AGENTS.md; this guard is what makes it hold.

Scope, and why it stops where it does
-------------------------------------
`##` through `######`. H1 is excluded: in this repository H1 is the document
title (there is no frontmatter `title` field — the `---` lines in docs/ja/ are
horizontal rules), and a title is a one-line claim, which is a different
convention. English headings are excluded because `Deleting a volume` and `How to
choose` are both correct English. Fenced blocks are excluded because `# コピー元で
実行しておく` inside ```bash is a shell comment.

A heading that is narrative rather than a label — a timeline entry, advice whose
imperative tone *is* the content, a stated intention — cannot be nominalised
without losing what it says. Those carry `<!-- allow:heading-style -->` on the
heading line, and the surrounding prose says why.

Exit codes: 0 every Japanese section heading is a noun phrase, 1 at least one is
not. `--selftest` proves the detector both fires and stays quiet.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {
    ".git",
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "__pycache__",
    ".private",
    ".kiro",
    ".aws-sam",
    ".pytest_cache",
    ".ruff_cache",
}

HEADING = re.compile(r"^(#{2,6})\s+(.*?)\s*$")
FENCE = re.compile(r"^\s*(?:```|~~~)")
ALLOW = re.compile(r"<!--\s*allow:heading-style\s*-->")
JAPANESE = re.compile(r"[ぁ-んァ-ヶ一-龠]")

# The character class holds the u-row only. A Japanese verb in its terminal form
# ends on the u-row.
#
#   `れ` must not be in it. That is the e-row, never a terminal form, and a bare
#   `れ` is the nominalised continuative (流れ / 崩れ / 遅れ / ずれ) — an open
#   class of nouns that an allowlist cannot close.
#
#   `ない` is listed literally rather than folded into `い$`. A plain negative
#   (…できない) is a sentence, but `問い` and `扱い` are nouns; `い$` would have
#   to be waived for both, and dropping the negative would let a whole family of
#   predicative headings through silently.
VERBAL = re.compile(
    r"(?:ます|ません|ました|でした|です|ください|でしょうか|のか|か|ない|[うくぐすずつぬふぶむる])$"
)

# There is no noun allowlist here on purpose. Once `れ` is out of the class, every
# word such a list would have held (流れ / 崩れ / 遅れ) no longer matches VERBAL
# at all, so the list would never fire — and a rule that never fires still reads
# as a guarantee.


def violations(text: str) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    in_fence = False
    for n, line in enumerate(text.split("\n"), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or ALLOW.search(line):
            continue
        m = HEADING.match(line)
        if not m:
            continue
        h = ALLOW.sub("", m.group(2)).strip()
        if not JAPANESE.search(h):
            continue
        if VERBAL.search(h):
            found.append((n, m.group(1), h))
    return found


# Both directions are asserted. A check that cannot fail is indistinguishable
# from no check.
CASES = [
    ("## 自分の環境で確かめる", True),
    ("## 検証を自動化する", True),
    ("## なぜこの区分が必要か", True),
    ("## どう分けるか", True),
    ("## 読み取りがあります", True),
    ("## 面に分かれました", True),
    ("## 既定は「同一」です", True),
    ("## アクセスは成立する", True),
    ("## AWS 側からしか消せない", True),
    ("## この経路を見ていない", True),
    ("## 自環境での確認手順", False),
    ("## 必要な理由", False),
    ("## 読み取りの存在", False),
    ("## 解除の不可", False),
    ("## 追加する流れ", False),
    ("## 最小権限の崩れ", False),
    ("## 実測の遅れ", False),
    ("## 扱う問い", False),
    ("## 権限の扱い", False),
    ("## よくある誤解", False),
    ("## 判断フロー", False),
    ("## ログの保存先", False),
    ("## リスクの一覧", False),
    ("## Deleting a volume", False),
    ("## How to choose", False),
    ("# タイトルは主張文で書く", False),
    ("## 15:29 気付く <!-- allow:heading-style -->", False),
]


def selftest() -> int:
    bad = [(c, want) for c, want in CASES if bool(violations(c)) != want]
    if violations("```bash\n# コピー元で実行しておく\n```\n"):
        bad.append(("fence", False))
    for c, want in bad:
        print(f"selftest FAIL (expected flag={want}): {c}", file=sys.stderr)
    if bad:
        return 1
    print(f"selftest: {len(CASES) + 1} case(s) passed")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    total = 0
    for p in sorted(ROOT.rglob("*.md")):
        if any(part in SKIP for part in p.parts):
            continue
        hits = violations(p.read_text(encoding="utf-8"))
        if not hits:
            continue
        print(f"\n{p.relative_to(ROOT)}")
        for n, h, t in hits:
            print(f"  L{n:>4} {h} {t}")
        total += len(hits)
    if total:
        print(
            f"\n{total} 件が体言止めではありません。接尾語で断定を保って名詞化してください。",
            file=sys.stderr,
        )
        return 1
    print("heading style: all Japanese section headings are noun phrases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
