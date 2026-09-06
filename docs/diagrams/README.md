# Architecture diagrams

Four figures drawn with the official AWS Architecture Icons, in Japanese and English.
The `.drawio` files here are **generated** — edit
[`scripts/build_diagrams.py`](../../scripts/build_diagrams.py) and rebuild, never the XML.

| Figure | Source | SVG (adapts to light/dark) | PNG light (2x) | PNG dark (2x) |
|---|---|---|---|---|
| File path — NFS in, access point out | [ja](architecture-file-path.drawio) / [en](architecture-file-path-en.drawio) | [ja](../images/architecture-file-path.svg) / [en](../images/architecture-file-path-en.svg) | [ja](../images/png/architecture-file-path@2x.png) / [en](../images/png/architecture-file-path-en@2x.png) | [ja](../images/png/architecture-file-path-dark@2x.png) / [en](../images/png/architecture-file-path-en-dark@2x.png) |
| API paths — MQTT and cellular | [ja](architecture-api-paths.drawio) / [en](architecture-api-paths-en.drawio) | [ja](../images/architecture-api-paths.svg) / [en](../images/architecture-api-paths-en.svg) | [ja](../images/png/architecture-api-paths@2x.png) / [en](../images/png/architecture-api-paths-en@2x.png) | [ja](../images/png/architecture-api-paths-dark@2x.png) / [en](../images/png/architecture-api-paths-en-dark@2x.png) |
| Pattern 01 — edge AI + Amazon Bedrock | [ja](pattern-01-edge-ai-bedrock.drawio) / [en](pattern-01-edge-ai-bedrock-en.drawio) | [ja](../images/pattern-01-edge-ai-bedrock.svg) / [en](../images/pattern-01-edge-ai-bedrock-en.svg) | [ja](../images/png/pattern-01-edge-ai-bedrock@2x.png) / [en](../images/png/pattern-01-edge-ai-bedrock-en@2x.png) | [ja](../images/png/pattern-01-edge-ai-bedrock-dark@2x.png) / [en](../images/png/pattern-01-edge-ai-bedrock-en-dark@2x.png) |
| Pattern 05 — agentic RAG | [ja](pattern-05-agentic-rag.drawio) / [en](pattern-05-agentic-rag-en.drawio) | [ja](../images/pattern-05-agentic-rag.svg) / [en](../images/pattern-05-agentic-rag-en.svg) | [ja](../images/png/pattern-05-agentic-rag@2x.png) / [en](../images/png/pattern-05-agentic-rag-en@2x.png) | [ja](../images/png/pattern-05-agentic-rag-dark@2x.png) / [en](../images/png/pattern-05-agentic-rag-en-dark@2x.png) |

No figure carries a notes box or a `※` marker. The constraints they used to state are in
the prose around each figure — the table under figure 1 in the READMEs, and the 前提と制約
sections of the pattern pages. See [No figure carries a notes box](#no-figure-carries-a-notes-box)
for why.

## Which file to reference

**In this repository, use the SVG.** One file covers both colour schemes. draw.io writes
each of our colours as a CSS `light-dark()` pair together with `color-scheme: light dark`,
so a reader in dark mode gets `#232F3E` text as `#bdc7d4` on a `#121212` background
without any markup on our side. No `<picture>` element, no `prefers-color-scheme`.

**Outside this repository — a blog, a slide — use the PNG**, and pick the theme by hand. A
raster cannot adapt, which is the only reason `-dark@2x.png` exists.

There is deliberately **no dark SVG**. Exporting the dark palette produces a file that
inverts in the opposite direction (`#D5DBDB` resolves to `#2e3333`), so pairing it with
`prefers-color-scheme: dark` would hand a dark-mode reader a light diagram. There is no
dark `.drawio` either: it is the same definitions with another palette, and committing it
would give one figure two sources.

Only our own strokes, text and fills change between the themes. The AWS icons are used
exactly as shipped in both — recolouring one is not permitted, and they read on either
background.

## Regenerating

The icon package is **not** in this repository. AWS licenses the assets for use in a
diagram, not for redistribution, so it has to be fetched and extracted somewhere outside
the working tree — the build refuses to finish if an `Arch_*` or `Res_*` file has landed
inside it.

```bash
# 1. Get the current package URL from the AWS asset page and extract it outside the repo
curl -sL https://aws.amazon.com/architecture/icons/ \
  | grep -oE 'https://[^"'"'"' ]*Icon[^"'"'"' ]*\.zip'
unzip -q -d /tmp/aws-icons <downloaded>.zip

# 2. Rebuild. Without --export only the .drawio files are written.
.venv/bin/python scripts/build_diagrams.py --icons /tmp/aws-icons --export
```

`--export` needs the draw.io desktop application, which the script expects at
`/Applications/draw.io.app/Contents/MacOS/draw.io` and which is not on `PATH`. Adjust
`DRAWIO_BIN` for another platform.

The dark-palette `.drawio` is written to a temporary directory, exported and dropped, so
`--export` is what produces the dark PNGs. Building without it leaves them untouched.

## What the build checks, and what it cannot

The script fails on a missing icon, on a Japanese label with no English mapping, on any
Japanese character surviving into the `-en` file, on XML that no longer parses, and on an
icon file having been copied into the repository.

None of that says the picture is right. A figure whose labels overlap and whose arrows run
through icons passes every one of those checks, so **look at the rendered PNG after every
change**. Both languages: English labels are wider than their Japanese equivalents and go
out of bounds first.

## Conventions the figures follow

Service icons are 80x80 and resource icons 48x48, at the size the package ships them —
never rescaled. Labels use the current official service names.

Two layout rules exist because breaking them is what produced the defects found in review:

- **A label sits below its icon, so nothing else may.** An edge never leaves an *icon*
  downwards; it exits the side and turns. A `box` is the exception, and only because its
  label is drawn inside it — `st` is exited downwards in two figures for that reason.
  Rows are 160 to 240px apart depending on whether the labels below them wrap to two
  lines; the 80px icon plus a two-line label at 16px needs about 130px before any gap.
- **Routing is stated, not inferred.** Left to itself an orthogonal edge takes the
  shortest path, and the shortest path regularly crosses an icon. Exit side, entry side
  and corners are given explicitly.

## Label size

`make diagram-fonts` enforces this, and it is part of `make check`. The numbers live in
`scripts/check_diagram_fonts.py`; the standard shared with the sibling repositories is
`~/.kiro/steering/global-document-readability.md`.

A label is displayed at the size it has **after** the image is scaled down to fit the column it sits
in, so a wider canvas makes every label smaller. The `fontSize` attribute alone says nothing about
legibility. Two floors, both required:

| Floor | Value | What it stops |
|---|---|---|
| Effective size — `fontSize × min(1, 880 / rendered width)` | **≥ 14px** | A label legible in the editor and not on the page |
| Source `fontSize` | **≥ 16px** | Meeting the first floor by shrinking the canvas rather than growing the text |

880px is the reader's column on GitHub and on the blog targets. The rendered width comes from the
exported SVG when one exists, not from `pageWidth`: draw.io crops to content and adds `--border`.

| Canvas width | Required `fontSize` |
|---|---|
| ≤ 880px | 16 |
| 1080px | 18 |
| 1238px | 20 |
| 1300px | 21 |

**Widening the canvas raises the floor**, so empty canvas is not free. It also interacts with the row
pitch: the old 220px figure was derived from an 80px icon plus a wrapped label at 11px, and a label at
the floor needs the pitch recomputed rather than the font reduced back.

When a compliant label stops fitting, work down this list. Shrinking the font is not on it.

1. Fold the label to two lines (two-line maximum; never break mid-word).
2. Move the notes box out of the figure and into body prose as a table.
3. Narrow the canvas toward 880px and stack elements vertically. Height does not compete for width.
4. Split the figure.
5. Abstract — collapse individual resources into the role they play.

### No figure carries a notes box

Step 2 of that list has been applied to all of them, so `diagram-font-debt.txt` is gone. Every figure
is built at `BODY_FONT = 16` on a canvas between 758 and 948px, and what the ※-marked boxes used to
say is now in the prose around each figure: a table under figure 1 in `README.md` and `README_en.md`,
and the 前提と制約 sections of the pattern pages.

Two consequences are worth stating, because both were the reason the boxes looked cheap:

- **A note fixed the canvas width at its own longest line.** The overview's box needed 1200px, which
  set the figure at 1300px, which is scaled to 0.68 in a reader's column — so the annotation was
  taking legibility from every label in the figure to buy its own.
- **The ※ markers were a second thing to keep in step.** They were numbered globally, across figures,
  because two figures sit next to each other in the README and a ※5 meaning two different things
  reads as one note. That had already happened once.

The one figure that could not be fixed by relayout was `architecture-overview`, which is now
`architecture-file-path` and `architecture-api-paths`. Thirteen cloud nodes and three site groups
need about 1300px at any font that survives the column, and the labels *are* the width — so raising
the font raised the canvas and gave the same amount back. It is split along the line the README
already drew: files written over NFS and read through the access point, against objects written with
the S3 API.
