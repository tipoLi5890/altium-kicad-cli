"""Gerber / Excellon fab-output reader (review M9).

Reads a fabrication output DIRECTORY into a lightweight :class:`GerberSet`:
per file its role (X2 ``TF.FileFunction`` attribute wins; filename convention
— KiCad and Protel-style extensions — is the fallback), units, extents in mm,
and aperture/tool/hole counts. This is deliberately NOT a renderer: extents
and roles are enough for the completeness / alignment / staleness checks,
and anything the parser cannot establish honestly lands in ``warnings``
instead of a guess (an Excellon file with format-ambiguous bare-integer
coordinates gets no bbox, not a wrong one).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_IN_MM = 25.4

# file kinds the checks reason about
KINDS = (
    "copper_top", "copper_bottom", "copper_inner",
    "mask_top", "mask_bottom", "paste_top", "paste_bottom",
    "silk_top", "silk_bottom", "outline", "drill", "drill_npth", "unknown",
)

# filename-convention fallback (KiCad tokens + Protel-style extensions)
_NAME_RULES: tuple[tuple[str, str], ...] = (
    (r"f_cu\.|_f_cu|\.gtl$", "copper_top"),
    (r"b_cu\.|_b_cu|\.gbl$", "copper_bottom"),
    (r"in\d+_cu|\.g\d+$|\.gp\d+$", "copper_inner"),
    (r"f_mask|\.gts$", "mask_top"),
    (r"b_mask|\.gbs$", "mask_bottom"),
    (r"f_paste|\.gtp$", "paste_top"),
    (r"b_paste|\.gbp$", "paste_bottom"),
    (r"f_silk|f_legend|\.gto$", "silk_top"),
    (r"b_silk|b_legend|\.gbo$", "silk_bottom"),
    (r"edge_cuts|outline|\.gko$|\.gm1$", "outline"),
    (r"npth", "drill_npth"),
    (r"\.drl$|\.xln$", "drill"),
)

_GERBER_EXTS = {".gbr", ".ger", ".gtl", ".gbl", ".gts", ".gbs", ".gto",
                ".gbo", ".gtp", ".gbp", ".gko", ".gm1", ".g1", ".g2", ".g3",
                ".g4", ".gp1", ".gp2"}
_DRILL_EXTS = {".drl", ".xln"}


@dataclass
class GerberFile:
    """One fab output file, reduced to what the checks need."""

    name: str
    kind: str = "unknown"
    function: str | None = None          # verbatim X2 TF.FileFunction value
    units: str | None = None             # "mm" | "in" | None
    bbox_mm: tuple[float, float, float, float] | None = None
    apertures: int = 0
    tools: int = 0
    holes: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class GerberSet:
    """Every recognised fab file under one directory."""

    source_path: str
    files: list[GerberFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def by_kind(self, kind: str) -> list[GerberFile]:
        return [f for f in self.files if f.kind == kind]

    def copper(self) -> list[GerberFile]:
        return [f for f in self.files if f.kind.startswith("copper_")]


# --------------------------------------------------------------------------- #
# kind classification
# --------------------------------------------------------------------------- #
def _kind_from_function(fn: str) -> str | None:
    parts = [p.strip().lower() for p in fn.split(",")]
    head = parts[0] if parts else ""
    side = parts[-1] if parts else ""
    if head == "copper":
        if side == "top":
            return "copper_top"
        if side in ("bot", "bottom"):
            return "copper_bottom"
        return "copper_inner"
    if head == "soldermask":
        return "mask_top" if side == "top" else "mask_bottom"
    if head == "paste":
        return "paste_top" if side == "top" else "paste_bottom"
    if head == "legend":
        return "silk_top" if side == "top" else "silk_bottom"
    if head == "profile":
        return "outline"
    if head == "nonplated":
        return "drill_npth"
    if head == "plated":
        return "drill"
    return None


def _kind_from_name(name: str) -> str:
    low = name.lower()
    for pattern, kind in _NAME_RULES:
        if re.search(pattern, low):
            return kind
    return "unknown"


# --------------------------------------------------------------------------- #
# RS-274X
# --------------------------------------------------------------------------- #
_FS_RX = re.compile(r"FS[LT][AI]X(\d)(\d)Y(\d)(\d)")
_COORD_RX = re.compile(r"X(-?\d+)|Y(-?\d+)")
_OP_RX = re.compile(r"D0?([123])\s*$")


def _parse_gerber(text: str, gf: GerberFile) -> None:
    scale = None                       # units → mm multiplier
    dec = None                         # decimal digits from %FS
    # extended (%...%) blocks first: units, format, apertures, attributes
    for block in re.findall(r"%([^%]*)%", text):
        for cmd in block.split("*"):
            cmd = cmd.strip()
            if not cmd:
                continue
            if cmd.startswith("MOMM"):
                gf.units, scale = "mm", 1.0
            elif cmd.startswith("MOIN"):
                gf.units, scale = "in", _IN_MM
            elif cmd.startswith("FS"):
                m = _FS_RX.match(cmd)
                if m:
                    dec = int(m.group(2))
                    if m.group(4) != m.group(2):
                        gf.warnings.append("asymmetric X/Y format")
            elif cmd.startswith("ADD"):
                gf.apertures += 1
            elif cmd.startswith("TF."):
                key, _, val = cmd[3:].partition(",")
                if key == "FileFunction":
                    gf.function = val
    if scale is None or dec is None:
        gf.warnings.append("missing %MO or %FS — coordinates skipped")
        return
    factor = scale / (10 ** dec)
    body = re.sub(r"%[^%]*%", "", text)
    x = y = 0
    xs: list[float] = []
    ys: list[float] = []
    for cmd in body.replace("\r", "").replace("\n", "").split("*"):
        if not cmd or not _OP_RX.search(cmd):
            continue
        seen = False
        for m in _COORD_RX.finditer(cmd):
            if m.group(1) is not None:
                x = int(m.group(1))
                seen = True
            else:
                y = int(m.group(2))
                seen = True
        op = _OP_RX.search(cmd).group(1)
        if seen and op in ("1", "2", "3"):
            xs.append(x * factor)
            ys.append(y * factor)
    if xs:
        gf.bbox_mm = (min(xs), min(ys), max(xs), max(ys))


# --------------------------------------------------------------------------- #
# Excellon
# --------------------------------------------------------------------------- #
_TOOL_RX = re.compile(r"^T\d+C[\d.]+", re.MULTILINE)
_XY_RX = re.compile(r"^X(-?[\d.]+)Y(-?[\d.]+)", re.MULTILINE)


def _parse_excellon(text: str, gf: GerberFile) -> None:
    up = text.upper()
    if "METRIC" in up:
        gf.units, scale = "mm", 1.0
    elif "INCH" in up:
        gf.units, scale = "in", _IN_MM
    else:
        scale = None
    gf.tools = len(_TOOL_RX.findall(up))
    xs: list[float] = []
    ys: list[float] = []
    ambiguous = False
    for m in _XY_RX.finditer(up):
        gf.holes += 1
        sx, sy = m.group(1), m.group(2)
        if scale is None:
            continue
        if "." not in sx and "." not in sy:
            ambiguous = True           # implied-decimal format: never guess
            continue
        xs.append(float(sx) * scale)
        ys.append(float(sy) * scale)
    if ambiguous:
        gf.warnings.append(
            "bare-integer coordinates (implied decimal) — bbox skipped "
            "rather than guessed")
    if scale is None and gf.holes:
        gf.warnings.append("missing METRIC/INCH — bbox skipped")
    if xs:
        gf.bbox_mm = (min(xs), min(ys), max(xs), max(ys))


# --------------------------------------------------------------------------- #
# directory reader
# --------------------------------------------------------------------------- #
def read_gerber_dir(path: str | Path) -> GerberSet:
    """Read every recognised fab file directly under ``path``."""
    root = Path(path)
    gs = GerberSet(source_path=str(root))
    if not root.is_dir():
        gs.warnings.append(f"not a directory: {root}")
        return gs
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            gs.warnings.append(f"{p.name}: unreadable ({exc})")
            continue
        is_drill = ext in _DRILL_EXTS or (
            ext == ".txt" and "M48" in text[:2000])
        is_gerber = ext in _GERBER_EXTS or (
            ext not in _DRILL_EXTS and "%FS" in text[:2000])
        if not is_drill and not is_gerber:
            continue
        gf = GerberFile(name=p.name)
        if is_drill:
            _parse_excellon(text, gf)
            gf.kind = _kind_from_name(p.name)
            if gf.kind == "unknown":
                gf.kind = "drill"
        else:
            _parse_gerber(text, gf)
            kind = (_kind_from_function(gf.function)
                    if gf.function else None)
            gf.kind = kind or _kind_from_name(p.name)
        gs.files.append(gf)
    if not gs.files:
        gs.warnings.append("no gerber/drill files recognised")
    return gs
