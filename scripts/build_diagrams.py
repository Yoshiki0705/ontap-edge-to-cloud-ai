#!/usr/bin/env python3
"""Build the architecture diagrams from their definitions in this file.

Why this exists
---------------
`.drawio` is the only source of truth for a diagram, and it is generated rather than
hand-edited so that a label change cannot land in one language and not the other. The
Japanese definition below is authoring; the English variant is produced by the LABELS
mapping, and a residue gate fails the build when a new Japanese label has no entry.

Icons come from the official AWS Architecture Icons asset package, which is not
committed: AWS permits using the assets in a diagram, not redistributing the library.
Pass the extracted package with --icons, and the SVG bytes end up base64-embedded in the
`.drawio` cells.

Traps this file exists to avoid, all of which produce a "successful" build with a
broken picture:

  1. `shape=image;image=data:image/svg+xml,<base64>` — comma, not `;base64,`. draw.io's
     parser expects the comma-only form, and the standard data URI form silently yields a
     blank icon. The MCP `insert_image_vertex` tool writes a form that renders in the
     editor and disappears on CLI export, which is why nothing here uses it.
  2. A double quote inside a `value="..."` attribute terminates it, and draw.io then
     drops that cell and every cell after it without an error. `xml_escape` below
     handles quotes for that reason; the stdlib `xml.sax.saxutils.escape` does not, and
     importing it also trips bandit's B406 for a function that parses nothing.
  3. An icon label sits *below* its 80px box and overflows sideways as far as the text
     needs, so "Amazon FSx for\nNetApp ONTAP" crosses the group boundary it belongs to.
     `whiteSpace=wrap` looks like the fix and is not: draw.io then wraps to the 80px box
     and breaks mid-word, producing "Amazon Quick" / "Sight" and "振動セン" / "サー".
     The official guidance is at most two lines and never a break inside a word, so the
     breaks are written into the label as `\n` and the layout gives each column the room
     a two-line name needs.
  4. An edge left to route itself takes the shortest orthogonal path, which is regularly
     straight through an icon or through the label under it. Because the label occupies
     the space directly below a box, an edge must never leave a box downwards. Hence the
     explicit exit/entry/waypoint arguments: routing is stated, not inferred.

Usage:
    python scripts/build_diagrams.py --icons /tmp/aws-icons [--export]

--export additionally renders SVG and PNG through the draw.io CLI, which is where a
layout problem actually becomes visible. XML validity proves nothing about the picture.

Exit codes: 0 built, 1 a definition, a mapping or an export failed.
"""

from __future__ import annotations

import argparse
import base64
import re
import subprocess  # nosec B404  # fixed argv, never a shell string
import sys
import tempfile
import xml.etree.ElementTree as ET  # nosec B405  # noqa: S405  parsing our own output
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_DIR = REPO_ROOT / "docs" / "diagrams"
IMAGE_DIR = REPO_ROOT / "docs" / "images"
PNG_DIR = IMAGE_DIR / "png"
DRAWIO_BIN = Path("/Applications/draw.io.app/Contents/MacOS/draw.io")

SERVICE = 80  # official service icon canvas; never rescaled
RESOURCE = 48  # official resource icon canvas

# Body text in a figure. 16 is the source-size floor in scripts/check_diagram_fonts.py,
# and every figure here is narrow enough that 16 also clears the effective floor.
BODY_FONT = 16
# A group's dashed frame carries its label in bold, one step up, as before at 11/12.
GROUP_FONT_OFFSET = 1

# Only our own strokes, text and fills change between themes. The AWS icons never do:
# recolouring one is not permitted, and they read on either background as shipped.
#
# The dark variant is a real palette rather than the draw.io CLI's `--theme dark`. That
# flag produces a genuinely dark PNG, but for SVG it only adds `color-scheme: dark` and a
# transparent background while leaving every explicit colour alone — measured: the
# stroke/fill census of a `--theme dark` SVG is identical to the light one. Rendered on a
# light page it is the light diagram. Exporting both formats from a dark-palette source
# also keeps the PNG and the SVG showing the same thing.
THEMES = {
    "light": {
        "ink": "#232F3E",
        "canvas": "#FFFFFF",
        "box_fill": "#FFFFFF",
    },
    # Contrast against the canvas: 12.6:1 for text, well past WCAG AA for body text.
    "dark": {
        "ink": "#D5DBDB",
        "canvas": "#16191F",
        "box_fill": "#232F3E",
    },
}


def edge_style(p: dict[str, str], size: int) -> str:
    return (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;"
        f"endArrow=open;endFill=0;strokeColor={p['ink']};strokeWidth=1;"
        f"fontSize={size};fontColor={p['ink']};labelBackgroundColor={p['canvas']};"
    )


def group_style(p: dict[str, str], size: int) -> str:
    return (
        "rounded=0;html=1;dashed=1;dashPattern=8 4;fillColor=none;"
        f"strokeColor={p['ink']};verticalAlign=top;align=left;spacingLeft=8;spacingTop=4;"
        f"fontSize={size};fontColor={p['ink']};fontStyle=1;"
    )


def plain_style(p: dict[str, str], size: int) -> str:
    return (
        f"rounded=1;html=1;whiteSpace=wrap;fillColor={p['box_fill']};"
        f"strokeColor={p['ink']};fontSize={size};fontColor={p['ink']};"
    )

# Icon paths relative to the extracted asset package. The filename is the authority on
# the service name: if a name cannot be found here, the name is wrong.
ICONS = {
    "fsxn": "Architecture-Service-Icons_07312026/Arch_Storage/64/Arch_Amazon-FSx-for-NetApp-ONTAP_64.svg",
    "bedrock": "Architecture-Service-Icons_07312026/Arch_Artificial-Intelligence/64/Arch_Amazon-Bedrock_64.svg",
    "agentcore": "Architecture-Service-Icons_07312026/Arch_Artificial-Intelligence/64/Arch_Amazon-Bedrock-AgentCore_64.svg",
    "athena": "Architecture-Service-Icons_07312026/Arch_Analytics/64/Arch_Amazon-Athena_64.svg",
    "glue": "Architecture-Service-Icons_07312026/Arch_Analytics/64/Arch_AWS-Glue_64.svg",
    "sagemaker": "Architecture-Service-Icons_07312026/Arch_Artificial-Intelligence/64/Arch_Amazon-SageMaker-AI_64.svg",
    "iotcore": "Architecture-Service-Icons_07312026/Arch_Internet-of-Things/64/Arch_AWS-IoT-Core_64.svg",
    "lambda": "Architecture-Service-Icons_07312026/Arch_Compute/64/Arch_AWS-Lambda_64.svg",
    "s3": "Architecture-Service-Icons_07312026/Arch_Storage/64/Arch_Amazon-Simple-Storage-Service_64.svg",
    "kinesis": "Architecture-Service-Icons_07312026/Arch_Analytics/64/Arch_Amazon-Kinesis-Data-Streams_64.svg",
    "firehose": "Architecture-Service-Icons_07312026/Arch_Analytics/64/Arch_Amazon-Data-Firehose_64.svg",
    "sns": "Architecture-Service-Icons_07312026/Arch_Application-Integration/64/Arch_Amazon-Simple-Notification-Service_64.svg",
    "opensearch": "Architecture-Service-Icons_07312026/Arch_Analytics/64/Arch_Amazon-OpenSearch-Service_64.svg",
    "quick": "Architecture-Service-Icons_07312026/Arch_Business-Applications/64/Arch_Amazon-Quick_64.svg",
    "s3ap": "Resource-Icons_07312026/Res_Storage/Res_Amazon-Simple-Storage-Service_General-Access-Points_48.svg",
    "camera": "Resource-Icons_07312026/Res_IoT/Res_AWS-IoT_Thing_Camera_48.svg",
    "vibration": "Resource-Icons_07312026/Res_IoT/Res_AWS-IoT_Thing_Vibration-Sensor_48.svg",
}

# Reference markers are global, not per figure. Two figures sit next to each other in the
# README, so a number that means one thing in one and something else in the other is read as
# the same note. That happened once already: the overview and pattern 05 both grew a ※5.
#
#   ※1 access point prerequisites      ※6 permission asymmetry
#   ※2 two-layer authorization         ※7 a standard S3 bucket is required here
#   ※3 event notifications unavailable ※8 no official walkthrough via an access point
#   ※4 hardware testing incomplete     ※9 optional path, not created by default
#   ※5 not implemented in this repository
#
# Japanese label -> English label. A Japanese label with no entry fails the build.
LABELS = {
    "AWS クラウド": "AWS Cloud",
    "オンプレミス": "On-premises",
    "既存のファイル共有": "Existing file share",
    "カメラ": "Camera",
    "振動センサー": "Vibration sensor",
    "ローカルストレージ": "Local storage",
    "Kafka / ClickHouse": "Kafka / ClickHouse",
    "ダッシュボード": "Dashboards",
    "文書": "Documents",
    "ベクトルストア": "Vector store",
    "利用者": "Users",
    "NFS / SMB": "NFS / SMB",
    "NFS 書き込み": "NFS write",
    "イベント": "Events",
    "同期": "Sync",
    "同期 / 読み取り配信": "Sync / read delivery",
    # Markers tie a note to the thing it qualifies. A note with nothing to point at is
    # read as a general disclaimer, which is not what these say.
    "エッジ拠点": "Edge site",
    "セルラー接続（任意）": "Cellular connectivity (optional)",
    "SORACOM\nプラットフォーム": "SORACOM\nplatform",
    "Amazon Bedrock\nKnowledge Bases": "Amazon Bedrock\nKnowledge Bases",
    "Amazon Kinesis\nData Streams": "Amazon Kinesis\nData Streams",
    "Amazon Data\nFirehose": "Amazon Data\nFirehose",
    "Amazon Simple\nStorage Service": "Amazon Simple\nStorage Service",
    "Amazon\nSageMaker AI": "Amazon\nSageMaker AI",
    "MQTT": "MQTT",
    "PutObject": "PutObject",
    "テレメトリ": "Telemetry",
    "取り込み": "Ingestion",
    "スクリーニング": "Screening",
    "詳細判定": "Detailed verdict",
    "通知": "Notification",
    "判定結果": "Verdicts",
    "検索": "Retrieval",
    "問い合わせ": "Query",
}

# U+203B (※) sits outside every CJK block, so a reference marker would otherwise survive
# untranslated into the English file with the residue gate reporting nothing. U+3000-303F
# covers 、。「」 for the same reason.
CJK = re.compile(r"[\u203b\u3000-\u303f\u3040-\u30ff\u4e00-\u9fff\uff00-\uffef]")


def xml_escape(text: str, newlines: bool = False) -> str:
    """Escape for use inside a double-quoted XML attribute value.

    Ampersand first: escaping it after `<` would turn `&lt;` into `&amp;lt;`.
    """
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return escaped.replace("\n", "&#10;") if newlines else escaped


def label_html(text: str) -> str:
    """Escape a label, turning an explicit `\\n` into a line break draw.io honours.

    `&#10;` is not a break in an HTML label; `<br>` is, and it has to reach the file
    escaped because an attribute value cannot hold a raw `<`.
    """
    return "&lt;br&gt;".join(xml_escape(part) for part in text.split("\n"))


class Diagram:
    """Accumulates cells and writes a `.drawio` whose XML is verified after writing."""

    def __init__(self, name: str, title: str, width: int, height: int,
                 theme: str = "light", font: int = BODY_FONT) -> None:
        self.name = name
        self.title = title
        self.width = width
        self.height = height
        self.theme = theme
        self.p = THEMES[theme]
        # A label is read at the size it has *after* the image is scaled into the column
        # it sits in, so the figure's width and this number are one decision, not two.
        # scripts/check_diagram_fonts.py holds the floors and fails on either.
        self.font = font
        self.cells: list[str] = []
        self.labels: list[str] = []

    def _value(self, text: str) -> str:
        return xml_escape(text, newlines=True)

    def group(self, cid: str, label: str, x: int, y: int, w: int, h: int) -> None:
        self.labels.append(label)
        self.cells.append(
            f'<mxCell id="{cid}" value="{label_html(label)}" style="{group_style(self.p, self.font + GROUP_FONT_OFFSET)}" '
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" '
            f'height="{h}" as="geometry"/></mxCell>'
        )

    def icon(self, cid: str, icon_key: str, label: str, x: int, y: int, uri: str,
             size: int = SERVICE) -> None:
        self.labels.append(label)
        style = (
            "sketch=0;html=1;shape=image;verticalLabelPosition=bottom;verticalAlign=top;"
            f"labelPosition=center;align=center;imageAspect=1;aspect=fixed;fontSize={self.font};"
            f"fontColor={self.p['ink']};image={uri};"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{label_html(label)}" style="{style}" '
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{size}" '
            f'height="{size}" as="geometry"/></mxCell>'
        )

    def box(self, cid: str, label: str, x: int, y: int, w: int, h: int) -> None:
        self.labels.append(label)
        self.cells.append(
            f'<mxCell id="{cid}" value="{label_html(label)}" style="{plain_style(self.p, self.font)}" '
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" '
            f'height="{h}" as="geometry"/></mxCell>'
        )

    def edge(self, cid: str, source: str, target: str, label: str = "",
             offset: tuple[float, int, int] | None = None,
             exit: tuple[float, float] | None = None,
             entry: tuple[float, float] | None = None,
             points: list[tuple[int, int]] | None = None,
             both: bool = False) -> None:
        """Connect two cells along a stated route.

        exit/entry are fractions of the source/target box, so (1, 0.5) is the middle of
        the right edge. Leave them off only when the two boxes are already aligned and
        the automatic route is a single straight segment. `points` are the corners the
        line must turn at; `both` draws an arrowhead at each end, which is how a
        bidirectional relationship stays one line instead of two overlapping ones.

        offset is (along, dx, dy). `along` runs from -1 at the source to +1 at the
        target, so the midpoint is 0 — not 0.5. Passing 0.5 puts the label three
        quarters of the way along, which is how a label ends up on top of the icon it
        was meant to sit beside.
        """
        if label:
            self.labels.append(label)
        style = edge_style(self.p, self.font)
        if exit is not None:
            style += f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;"
        if entry is not None:
            style += f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
        if both:
            style += "startArrow=open;startFill=0;"

        inner = ""
        if offset is not None:
            inner += f'<mxPoint as="offset" x="{offset[1]}" y="{offset[2]}"/>'
        if points:
            corners = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points)
            inner += f'<Array as="points">{corners}</Array>'
        along = f' x="{offset[0]}"' if offset is not None else ""
        geometry = (
            f'<mxGeometry{along} relative="1" as="geometry">{inner}</mxGeometry>'
            if inner else '<mxGeometry relative="1" as="geometry"/>'
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{self._value(label)}" style="{style}" '
            f'edge="1" parent="1" source="{source}" target="{target}">{geometry}</mxCell>'
        )

    def to_xml(self) -> str:
        body = "".join(self.cells)
        return (
            '<mxfile host="build_diagrams.py">'
            f'<diagram name="{self._value(self.title)}">'
            f'<mxGraphModel dx="{self.width}" dy="{self.height}" grid="0" '
            'gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
            f'page="1" pageScale="1" pageWidth="{self.width}" '
            f'pageHeight="{self.height}" math="0" shadow="0" '
            # Without this the export is transparent, and a dark figure with light text
            # is invisible on the light page it gets embedded in.
            f'background="{self.p["canvas"]}">'
            '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            f"{body}</root></mxGraphModel></diagram></mxfile>"
        )

    def write(self, path: Path) -> None:
        xml = self.to_xml()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Trailing newline: end-of-file-fixer rewrites the file without one, and a
        # generated artifact that a hook wants to edit is a build that is never clean.
        path.write_text(xml + "\n", encoding="utf-8")
        # A gate, not a formality: a dropped cell is invisible without it.
        ET.parse(path)  # nosec B314  # noqa: S314  our own generated file
        for cell in re.findall(r'id="([^"]+)"', xml):
            if f'id="{cell}"' not in path.read_text(encoding="utf-8"):
                raise SystemExit(f"{path}: cell {cell} did not land in the file")


def data_uri(icons_root: Path, key: str) -> str:
    path = icons_root / ICONS[key]
    if not path.is_file():
        raise SystemExit(f"icon not found: {path}")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    # Comma, not ";base64,". The standard data URI form renders blank in draw.io.
    return f"data:image/svg+xml,{b64}"


def translate(diagram: Diagram) -> Diagram:
    """Produce the English variant, failing when a label has no mapping."""
    xml = diagram.to_xml()
    missing = sorted({label for label in diagram.labels if CJK.search(label) and label not in LABELS})
    if missing:
        for label in missing:
            print(f"  no LABELS entry for: {label!r}", file=sys.stderr)
        raise SystemExit(f"{diagram.name}: {len(missing)} label(s) have no translation")

    english = Diagram(diagram.name + "-en", diagram.title, diagram.width,
                      diagram.height, diagram.theme)
    # Longest first: "エッジ拠点 ※4" has to be replaced before "エッジ拠点" would
    # consume its prefix and leave the marker behind.
    for ja, en in sorted(LABELS.items(), key=lambda kv: -len(kv[0])):
        xml = xml.replace(label_html(ja), label_html(en))
    english.cells = [xml]  # already a full document; write() handles it below
    english._prebuilt = xml  # type: ignore[attr-defined]
    return english


def write_english(xml: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml + "\n", encoding="utf-8")
    ET.parse(path)  # nosec B314  # noqa: S314  our own generated file
    residue = CJK.findall(path.read_text(encoding="utf-8"))
    if residue:
        raise SystemExit(
            f"{path}: {len(residue)} CJK character(s) remain after translation: "
            f"{''.join(sorted(set(residue))[:20])}"
        )


# --------------------------------------------------------------------------------------
# Diagram definitions
# --------------------------------------------------------------------------------------


def file_path(uri, theme: str) -> Diagram:
    """The file-protocol path: an edge site writes files, and the cloud reads them.

    This and `api_paths` are the two halves of what used to be one `architecture-overview`.
    One figure could not be made readable. Thirteen cloud nodes plus three site groups need
    roughly 1300px of width at any font size that survives a reader's column, and the
    labels are the width -- so every attempt to raise the font raised the canvas and lost
    the same amount again. The split follows the line the README already draws: files
    written over NFS and read through the access point, against objects written with the S3
    API. A reader who wants one of them does not need the other in frame.

    The site groups sit *above* the cloud rather than beside it, which is what frees the
    width. The sync edge therefore leaves `st` downwards -- allowed because `st` is a box,
    whose label is drawn inside it, unlike an icon whose label occupies the space below.

    The notes box is gone. What it carried is a table under the figure in README.md and
    README_en.md, where a line can be as long as it needs to be and can link to the page
    that holds the detail. The ※ markers went with it: a marker pointing at a note that is
    not in the frame reads as a footnote the reader is expected to hunt for.
    """
    d = Diagram("architecture-file-path", "File path", 880, 1100, theme)
    d.group("g_edge", "エッジ拠点", 40, 60, 300, 350)
    d.group("g_onprem", "オンプレミス", 380, 60, 280, 350)
    d.group("g_cloud", "AWS クラウド", 40, 490, 800, 570)

    d.icon("cam", "camera", "カメラ", 80, 110, uri("camera"), RESOURCE)
    # 200, not 220: this label is the widest in the group and the English form
    # ("Vibration sensor") is wider still, which put its right edge under the riser
    # carrying the write into local storage.
    d.icon("vib", "vibration", "振動センサー", 200, 110, uri("vibration"), RESOURCE)
    # Centred on x=140 so the sync edge into the file system below is one straight segment.
    d.box("st", "ローカルストレージ", 55, 310, 170, 50)
    d.box("kc", "Kafka / ClickHouse", 400, 130, 240, 50)
    d.box("dash", "ダッシュボード", 400, 250, 240, 40)

    d.icon("fsxn", "fsxn", "Amazon FSx for\nNetApp ONTAP", 100, 750, uri("fsxn"))
    d.icon("s3ap", "s3ap", "S3 Access Point", 300, 766, uri("s3ap"), RESOURCE)
    # Three consumers of one access point, fanned into their own rows. Each riser sits in
    # the corridor between the access point's label and the consumers', which is the only
    # vertical space in the row that belongs to no label.
    d.icon("bed", "bedrock", "Amazon Bedrock", 540, 590, uri("bedrock"))
    d.icon("ath", "athena", "Amazon Athena", 540, 750, uri("athena"))
    # The AWS list of services with a published access-point walkthrough covers Athena,
    # Lambda, Glue, Bedrock Knowledge Bases, EMR Serverless, CloudFront and Transfer
    # Family. SageMaker AI is not on it, and the README table under this figure says so --
    # an unqualified line here would read as a support claim this project cannot make.
    d.icon("sm", "sagemaker", "Amazon\nSageMaker AI", 540, 910, uri("sagemaker"))
    # The icon package ships only a suite-level Quick icon; the node here is the BI
    # capability, which the docs call Amazon Quick Sight.
    d.icon("quick", "quick", "Amazon\nQuick Sight", 710, 750, uri("quick"))

    # The label sits on the riser, below where the sensor labels end. Placed on the
    # horizontal stub instead it lands on top of the vibration sensor's own label.
    d.edge("e1", "cam", "st", "NFS 書き込み", (0, 50, 0),
           exit=(1, 0.5), entry=(0.65, 0), points=[(165, 134)])
    # Into the right-hand side at 0.3, not the middle: the sync line arrives at the bottom
    # and two arrowheads on one point read as one arrow. The two edges leaving this sensor
    # exit at different heights, or they overlap for the first 30px and read as one line.
    d.edge("e2", "vib", "st",
           exit=(1, 0.8), entry=(1, 0.3), points=[(325, 148), (325, 325)])
    d.edge("e3", "vib", "kc", "イベント", (0, 0, -14),
           exit=(1, 0.3), entry=(0, 0.5), points=[(350, 124), (350, 155)])
    d.edge("e5", "kc", "dash")
    # One line with two heads: the site both pushes new files up and reads cached data
    # back down. The label lands in the 80px gap between the two bands.
    # -0.55 along, not 0: the midpoint of a segment this long is inside the cloud group,
    # and a label about the site's own sync belongs in the gap between the two bands.
    d.edge("e4", "st", "fsxn", "同期 / 読み取り配信", (-0.55, 116, 0),
           exit=(0.5, 1), entry=(0.5, 0), both=True)
    d.edge("e6", "fsxn", "s3ap", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e7", "s3ap", "bed",
           exit=(1, 0.25), entry=(0, 0.5), points=[(440, 778), (440, 630)])
    d.edge("e8", "s3ap", "ath", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e9", "s3ap", "sm",
           exit=(1, 0.75), entry=(0, 0.5), points=[(470, 802), (470, 950)])
    d.edge("e10", "ath", "quick", exit=(1, 0.5), entry=(0, 0.5))
    return d


def api_paths(uri, theme: str) -> Diagram:
    """The two paths that write with the S3 API rather than a file protocol.

    The MQTT path puts every object through the access point -- `Bucket=S3AP_ARN` at all
    three call sites in `cloud/iot_ingestion/handler.py`, and its template declares no
    bucket at all. The cellular path is the one place a standard bucket is real:
    `cloud/ingestion/template.yaml` creates `DataLakeBucket`, Firehose delivers to it and
    Glue crawls it.

    SORACOM is not edge equipment. `SoracomIngestionRole` is assumed by SORACOM's own AWS
    account with the Operator ID as `ExternalId`, so the writer is their platform, and the
    whole path is optional -- nothing here is created unless `SoracomOperatorId` is passed.
    The README table under the figure carries both facts.

    Glue's catalogue is what Athena queries, and Athena is in the file-path figure rather
    than repeated here. The README flow list states the hand-off; drawing the same service
    twice across two figures would invite reading them as two different Athenas.
    """
    d = Diagram("architecture-api-paths", "API paths", 880, 860, theme)
    d.group("g_cellular", "セルラー接続（任意）", 40, 60, 300, 150)
    d.group("g_cloud", "AWS クラウド", 40, 290, 800, 520)

    # The break is written in. Left to wrap, a 170px box splits this at
    # "プラットフ / ォーム", mid-word, which the official guidance rules out.
    d.box("soracom", "SORACOM\nプラットフォーム", 45, 105, 190, 50)

    d.icon("kin", "kinesis", "Amazon Kinesis\nData Streams", 100, 390, uri("kinesis"))
    d.icon("fh", "firehose", "Amazon Data\nFirehose", 300, 390, uri("firehose"))
    d.icon("s3", "s3", "Amazon Simple\nStorage Service", 500, 390, uri("s3"))
    d.icon("glue", "glue", "AWS Glue", 700, 390, uri("glue"))

    d.icon("iot", "iotcore", "AWS IoT Core", 100, 630, uri("iotcore"))
    d.icon("lam", "lambda", "AWS Lambda", 300, 630, uri("lambda"))
    d.icon("s3ap", "s3ap", "S3 Access Point", 500, 646, uri("s3ap"), RESOURCE)
    d.icon("fsxn", "fsxn", "Amazon FSx for\nNetApp ONTAP", 680, 630, uri("fsxn"))

    # Just past the group's bottom edge, in the gap. At the segment's own midpoint the
    # label lands inside the cloud group; pulled all the way to -0.5 it sits on the
    # dashed border it is meant to be clear of.
    d.edge("e1", "soracom", "kin", "テレメトリ", (-0.1, 84, 0),
           exit=(0.5, 1), entry=(0.5, 0))
    d.edge("e2", "kin", "fh", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e3", "fh", "s3", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e4", "s3", "glue", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e5", "iot", "lam", "MQTT", (0, 0, -14), exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e6", "lam", "s3ap", "PutObject", (0, 0, -14), exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e7", "s3ap", "fsxn", exit=(1, 0.5), entry=(0, 0.5))
    return d



def pattern01(uri, theme: str) -> Diagram:
    """The edge group sits *above* the cloud group rather than beside it.

    Side by side, the edge group and the gap after it spend 380px of width that the
    cloud's four columns then have to fit around, and at BODY_FONT they do not: the labels
    alone need about 1030px, which arrives in a reader's column at under 14px. Stacked, the
    same four columns start at x=40 and the whole figure fits in a canvas narrow enough
    that no downscaling happens at all.

    The cost is that the sync edge now leaves `st` downwards. That is allowed here and only
    here: `st` is a box, whose label is drawn *inside* it, so nothing sits in the space
    below. For an icon the label is below the 80px box, which is why an icon is never
    exited downwards.

    The notes box is gone, and with it the ※3 / ※4 / ※7 markers. ※3 and ※4 were already
    stated at more length in `docs/ja/aws-patterns/01-edge-ai-bedrock.md`; ※7 was not, and
    is now a bullet in that page's 前提と制約 pointing at the table that carries the detail.
    """
    d = Diagram("pattern-01-edge-ai-bedrock", "Pattern 01", 800, 900, theme)
    d.group("g_edge", "エッジ拠点", 40, 60, 300, 260)
    # 60px of clear air between the groups so the label on the line that crosses the
    # boundary sits in the gap instead of on a dashed border.
    d.group("g_cloud", "AWS クラウド", 40, 380, 720, 480)

    # Camera above the storage in one column, so the write is a single straight segment.
    d.icon("cam", "camera", "カメラ", 116, 110, uri("camera"), RESOURCE)
    d.box("st", "ローカルストレージ", 55, 240, 170, 50)

    d.icon("fsxn", "fsxn", "Amazon FSx for\nNetApp ONTAP", 100, 460, uri("fsxn"))
    d.icon("s3ap", "s3ap", "S3 Access Point", 270, 476, uri("s3ap"), RESOURCE)
    d.icon("lam1", "lambda", "AWS Lambda", 440, 460, uri("lambda"))
    d.icon("bed1", "bedrock", "Amazon Bedrock", 610, 460, uri("bedrock"))
    # RESULT_BUCKET in the use-case templates is the shared stack's standard bucket, and
    # Athena reads the verdicts from it.
    d.icon("s3", "s3", "Amazon Simple\nStorage Service", 100, 700, uri("s3"))
    d.icon("lam2", "lambda", "AWS Lambda", 440, 700, uri("lambda"))
    d.icon("sns", "sns", "Amazon Simple\nNotification Service", 610, 700, uri("sns"))

    d.edge("e1", "cam", "st", "NFS 書き込み", (0, 62, 0))
    # -0.2 along: at the segment's own midpoint the label straddles the cloud group's
    # top border, and a label with a background then reads as a gap in the frame.
    d.edge("e2", "st", "fsxn", "同期", (-0.2, 24, 0), exit=(0.5, 1), entry=(0.5, 0))
    d.edge("e3", "fsxn", "s3ap", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e4", "s3ap", "lam1", "スクリーニング", (0, 0, -14),
           exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e5", "lam1", "bed1", exit=(1, 0.5), entry=(0, 0.5))
    # Out to a riser at x=390, clear to the left of every label on both rows, then in from
    # above. A straight drop would run through this icon's own label.
    d.edge("e6", "lam1", "lam2", "詳細判定", (0, -34, 0),
           exit=(0, 0.85), entry=(0.5, 0), points=[(390, 528), (390, 660), (480, 660)])
    d.edge("e7", "lam2", "sns", "通知", (0, 0, -14), exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e8", "lam2", "s3", "判定結果", (0, 0, -14), exit=(0, 0.5), entry=(1, 0.5))
    return d


def pattern05(uri, theme: str) -> Diagram:
    """Ingest across the top band, retrieval across the bottom one.

    990px wide, not 1080. At BODY_FONT the labels are wider, so the reflex is a wider
    canvas -- and a wider canvas is scaled down further in the reader's column, which
    makes every label smaller again. The width comes down instead: the left group is
    narrowed to what its 200px boxes need, and the query riser is pulled in from 930 to
    890. That lands the exported figure at ~928px, so 16 arrives at about 15px.

    The notes box is gone. Both items it carried are in
    `docs/ja/aws-patterns/05-agentic-rag.md` and its English counterpart -- that the
    repository has no implementation and AWS documents one, and the permission asymmetry
    -- each already stated at more length than a box in a figure can hold. The ※5 and ※6
    markers go with it: a marker whose note is not in the frame reads as a footnote the
    reader is expected to find, and there is nothing to find.
    """
    d = Diagram("pattern-05-agentic-rag", "Pattern 05", 990, 600, theme)
    d.group("g_onprem", "既存のファイル共有", 40, 60, 240, 300)
    # 590 wide: the group has to contain the query riser at x=890 and the label centred
    # on it, or the label crosses the boundary. Left edge at 360 keeps the 80px
    # inter-group gap the other figures use, which is where the crossing edge's label sits.
    d.group("g_cloud", "AWS クラウド", 360, 60, 590, 480)

    d.box("users", "利用者", 60, 110, 200, 40)
    d.box("docs", "文書", 60, 240, 200, 50)

    d.icon("fsxn", "fsxn", "Amazon FSx for\nNetApp ONTAP", 410, 140, uri("fsxn"))
    d.icon("s3ap", "s3ap", "S3 Access Point", 585, 156, uri("s3ap"), RESOURCE)
    # Knowledge Bases by name: that is the integration AWS documents for an access
    # point, via the alias. Plain model invocation has no such walkthrough, and the
    # doc's own mermaid already said Knowledge Bases while this figure did not.
    d.icon("bed", "bedrock", "Amazon Bedrock\nKnowledge Bases", 750, 140, uri("bedrock"))
    d.icon("os", "opensearch", "Amazon OpenSearch\nService", 585, 380, uri("opensearch"))
    d.icon("agent", "agentcore", "Amazon Bedrock\nAgentCore", 750, 380, uri("agentcore"))

    d.edge("e1", "users", "docs", "NFS / SMB", (0, 44, 0))
    d.edge("e2", "docs", "fsxn", "同期", (0, 0, -14),
           exit=(1, 0.5), entry=(0, 0.5), points=[(320, 265), (320, 180)])
    d.edge("e3", "fsxn", "s3ap", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e4", "s3ap", "bed", "取り込み", (0, 0, -14), exit=(1, 0.5), entry=(0, 0.5))
    # Leaves Bedrock sideways and comes back over the top of OpenSearch: a straight drop
    # would run through Bedrock's own label.
    d.edge("e5", "bed", "os", "ベクトルストア", (0, -60, 0),
           exit=(0, 0.9), entry=(0.5, 0), points=[(710, 212), (710, 340), (625, 340)])
    d.edge("e6", "agent", "os", "検索", (0, 0, -14), exit=(0, 0.5), entry=(1, 0.5))
    # Round the right-hand side rather than up the shared column, which holds both
    # icons' labels. It enters Bedrock's right side at y=180, above where that label
    # begins.
    d.edge("e7", "agent", "bed", "問い合わせ", (0, 0, 0),
           exit=(1, 0.25), entry=(1, 0.5), points=[(890, 400), (890, 180)])
    return d


DEFINITIONS = (file_path, api_paths, pattern01, pattern05)


def run_export(source: Path, target: Path, extra: list[str]) -> None:
    if not DRAWIO_BIN.is_file():
        print(f"  draw.io not found at {DRAWIO_BIN}; skipping export", file=sys.stderr)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(  # nosec B603  # noqa: S603  fixed binary, no shell
        [str(DRAWIO_BIN), "--export", "--border", "12", *extra,
         "--output", str(target), str(source)],
        capture_output=True, text=True, check=False,
    )
    if not target.is_file() or target.stat().st_size == 0:
        print(result.stdout, result.stderr, file=sys.stderr)
        raise SystemExit(f"export produced nothing: {target}")
    # draw.io writes the SVG without a final newline; PNG is binary and left alone.
    if target.suffix == ".svg":
        body = target.read_bytes()
        if not body.endswith(b"\n"):
            target.write_bytes(body + b"\n")
    print(f"  {target.relative_to(REPO_ROOT)} ({target.stat().st_size // 1024} KB)")


def export_svg(source: Path, stem: str) -> None:
    """One SVG per figure, and it carries both themes.

    Left on the default theme, draw.io writes every colour as a CSS `light-dark()` pair
    plus `color-scheme: light dark`, so the viewer picks. Measured on these figures: 46
    such pairs, with #232F3E resolving to #bdc7d4 and #FFFFFF to #121212 under a dark
    scheme — a correct dark rendering of the light source, for free.

    That is also why there is no dark SVG. Exporting the dark palette this way inverts it
    the other way (#D5DBDB -> #2e3333), so serving a dark SVG to a dark-mode reader would
    hand them a light diagram. `--theme light|dark` pins the colours and would give a
    fixed pair, but one adaptive file is fewer artifacts and cannot be mismatched.
    """
    run_export(source, IMAGE_DIR / f"{stem}.svg", ["--format", "svg", "--embed-svg-images"])


def export_png(source: Path, stem: str) -> None:
    """PNG per figure per theme. A raster cannot adapt, so dark needs its own file.

    `--theme light` means "do not apply an inversion", not "make it light": the palette in
    the source decides. Without it the export depends on draw.io's default, which is how a
    dark source could silently come back light.
    """
    run_export(source, PNG_DIR / f"{stem}@2x.png",
               ["--format", "png", "--scale", "2", "--theme", "light"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--icons", required=True, type=Path,
                        help="extracted AWS Architecture Icons package (keep outside the repo)")
    parser.add_argument("--export", action="store_true", help="also render SVG and PNG")
    args = parser.parse_args()

    if not args.icons.is_dir():
        raise SystemExit(f"icon package not found: {args.icons}")

    def uri(key: str) -> str:
        return data_uri(args.icons, key)

    seen: set[str] = set()
    # Only the light `.drawio` is committed. The dark one is the same definitions with a
    # different palette, so keeping it would be a second source of truth for one figure;
    # it is written to a temporary directory, exported and dropped.
    with tempfile.TemporaryDirectory(prefix="diagrams-dark-") as scratch:
        dark_dir = Path(scratch)
        for build in DEFINITIONS:
            for theme in THEMES:
                suffix = "" if theme == "light" else f"-{theme}"
                directory = DIAGRAM_DIR if theme == "light" else dark_dir
                diagram = build(uri, theme)
                seen.update(diagram.labels)

                ja_path = directory / f"{diagram.name}{suffix}.drawio"
                diagram.write(ja_path)
                english = translate(diagram)
                en_path = directory / f"{diagram.name}-en{suffix}.drawio"
                write_english(english._prebuilt, en_path)  # type: ignore[attr-defined]
                for path in (ja_path, en_path):
                    if theme == "light":
                        print(path.relative_to(REPO_ROOT))
                    else:
                        print(f"(scratch) {path.name}")

                if args.export:
                    for path, stem in ((ja_path, f"{diagram.name}{suffix}"),
                                       (en_path, f"{diagram.name}-en{suffix}")):
                        if theme == "light":
                            export_svg(path, stem)
                        export_png(path, stem)

    stray = [
        p for p in REPO_ROOT.rglob("*")
        if p.is_file() and re.match(r"(Arch_|Res_|Icon-package)", p.name)
        and ".venv" not in p.parts
    ]
    if stray:
        raise SystemExit(f"icon library files must not be committed: {stray[:5]}")

    # A mapping nothing uses is a mapping nobody maintains, and the next reader cannot
    # tell a stale entry from one whose figure is still to come.
    unused = sorted(set(LABELS) - seen)
    if unused:
        for label in unused:
            print(f"  unused LABELS entry: {label!r}", file=sys.stderr)
        raise SystemExit(f"{len(unused)} LABELS entr(ies) match no label in any figure")

    print(f"diagrams: OK ({len(seen)} distinct labels, {len(LABELS)} translated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
