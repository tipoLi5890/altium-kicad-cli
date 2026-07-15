"""Fab-output review (M9): gerber completeness / alignment / staleness.

Runs when ``review analyze --gerbers DIR`` supplies a fab directory. The
staleness rule is the load-bearing one: an outline in the export that no
longer matches the board file means the fab package predates the last edit
— the classic "ordered the old rev" failure.
"""

from __future__ import annotations

from ...report import Finding, Severity
from .. import Detector, Rule, register
from .. import geometry

# copper/outline registrations should agree within this envelope
_ALIGN_TOL_MM = 2.0
# outline size vs the board file: beyond this the export is stale
_STALE_TOL_MM = 1.0

RULES = (
    Rule(
        code="REVIEW_GERBER_INCOMPLETE",
        title="Fab package is missing expected files",
        explain=(
            "A manufacturable package needs top+bottom copper, both solder "
            "masks, a board profile (outline) and a plated drill file; a "
            "missing silkscreen is only a note. File roles come from X2 "
            "TF.FileFunction attributes first, filename conventions second "
            "— an exotic naming scheme may need renaming rather than "
            "waiving."),
        default_severity="warning", confidence="deterministic", version="1",
        reference="Gerber X2 file functions (Ucamco): minimum fab set"),
    Rule(
        code="REVIEW_GERBER_LAYER_MISMATCH",
        title="Copper file count disagrees with the board's stackup",
        explain=(
            "The board file declares N copper layers but the export "
            "contains a different number of copper gerbers — layers were "
            "dropped from (or added to) the package."),
        default_severity="warning", confidence="deterministic", version="1",
        reference=None),
    Rule(
        code="REVIEW_GERBER_ALIGNMENT",
        title="Fab layers are not registered to each other",
        explain=(
            f"Copper/outline extents disagree by more than {_ALIGN_TOL_MM:g}"
            " mm, or drill hits fall outside the outline — layers exported "
            "with different origins or from different revisions. Extents "
            "are bounding boxes (stated), so a flagged package deserves a "
            "CAM-viewer look."),
        default_severity="warning", confidence="deterministic", version="1",
        reference=None),
    Rule(
        code="REVIEW_GERBER_STALE",
        title="Exported outline no longer matches the board file",
        explain=(
            "The outline gerber's size differs from the .kicad_pcb "
            f"Edge.Cuts extent by more than {_STALE_TOL_MM:g} mm: the fab "
            "package predates the last board edit. Re-export before "
            "ordering."),
        default_severity="warning", confidence="deterministic", version="1",
        reference=None),
    Rule(
        code="REVIEW_GERBER_UNITS_MIXED",
        title="Fab files mix units",
        explain=(
            "Some files are metric, others imperial. Legal, but a classic "
            "source of CAM import mistakes — re-export in one unit system "
            "if the fab allows."),
        default_severity="note", confidence="deterministic", version="1",
        reference=None),
)

_REQUIRED = (("copper_top", Severity.WARNING),
             ("copper_bottom", Severity.WARNING),
             ("mask_top", Severity.WARNING),
             ("mask_bottom", Severity.WARNING),
             ("outline", Severity.WARNING),
             ("drill", Severity.WARNING),
             ("silk_top", Severity.NOTE))


def _center(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _size(b):
    return (b[2] - b[0], b[3] - b[1])


def run(ctx) -> list[Finding]:
    gs = getattr(ctx, "gerbers", None)
    if gs is None:
        return []
    out: list[Finding] = []
    ev_files = {"source": "geometry",
                "calc": {"files": [f.name for f in gs.files]}}

    # completeness ---------------------------------------------------------
    missing = [(kind, sev) for kind, sev in _REQUIRED if not gs.by_kind(kind)]
    hard = [k for k, s in missing if s is Severity.WARNING]
    soft = [k for k, s in missing if s is Severity.NOTE]
    if hard:
        out.append(Finding(
            code="REVIEW_GERBER_INCOMPLETE", severity=Severity.WARNING,
            message=(f"fab package is missing: {', '.join(sorted(hard))} "
                     f"({len(gs.files)} file(s) recognised)"),
            refs=sorted(hard), confidence="deterministic",
            evidence=ev_files,
            remediation="re-export the full fabrication set"))
    if soft:
        out.append(Finding(
            code="REVIEW_GERBER_INCOMPLETE", severity=Severity.NOTE,
            message=f"fab package has no {', '.join(sorted(soft))}",
            refs=sorted(soft), confidence="deterministic",
            evidence=ev_files,
            remediation="export the silkscreen unless deliberately bare"))

    # stackup count vs the board file ---------------------------------------
    pcb = getattr(ctx, "pcb", None)
    board_cu = len(((getattr(pcb, "board", {}) or {}).get("copper_layers")
                    or [])) if pcb is not None else 0
    if board_cu and gs.copper() and len(gs.copper()) != board_cu:
        out.append(Finding(
            code="REVIEW_GERBER_LAYER_MISMATCH", severity=Severity.WARNING,
            message=(f"board declares {board_cu} copper layer(s) but the "
                     f"package holds {len(gs.copper())} copper gerber(s)"),
            refs=[f.name for f in gs.copper()], confidence="deterministic",
            evidence={"source": "geometry",
                      "calc": {"board_layers": board_cu,
                               "copper_files": len(gs.copper())}},
            remediation="re-export with every copper layer selected"))

    # units ------------------------------------------------------------------
    units = {f.units for f in gs.files if f.units}
    if len(units) > 1:
        out.append(Finding(
            code="REVIEW_GERBER_UNITS_MIXED", severity=Severity.NOTE,
            message=f"fab files mix units: {', '.join(sorted(units))}",
            refs=[], confidence="deterministic", evidence=ev_files,
            remediation="re-export in one unit system if the fab allows"))

    # alignment ----------------------------------------------------------------
    outline = next((f for f in gs.by_kind("outline") if f.bbox_mm), None)
    boxed = [f for f in gs.copper() if f.bbox_mm]
    if outline:
        boxed.append(outline)
    misaligned: list[str] = []
    for i, a in enumerate(boxed):
        for b in boxed[i + 1:]:
            (acx, acy), (bcx, bcy) = _center(a.bbox_mm), _center(b.bbox_mm)
            if max(abs(acx - bcx), abs(acy - bcy)) > _ALIGN_TOL_MM:
                misaligned.append(f"{a.name}↔{b.name}")
    if outline:
        ox0, oy0, ox1, oy1 = outline.bbox_mm
        for f in gs.files:
            if f.kind.startswith("drill") and f.bbox_mm:
                dx0, dy0, dx1, dy1 = f.bbox_mm
                if (dx0 < ox0 - _ALIGN_TOL_MM or dx1 > ox1 + _ALIGN_TOL_MM
                        or dy0 < oy0 - _ALIGN_TOL_MM
                        or dy1 > oy1 + _ALIGN_TOL_MM):
                    misaligned.append(f"{f.name}⇢outside outline")
    if misaligned:
        out.append(Finding(
            code="REVIEW_GERBER_ALIGNMENT", severity=Severity.WARNING,
            message=("layer registration disagrees: "
                     + "; ".join(sorted(misaligned)[:6])),
            refs=sorted(misaligned)[:6], confidence="deterministic",
            evidence={"source": "geometry",
                      "assumptions": ["extents compared as bounding boxes"]},
            remediation="re-export every layer from the same board revision "
                        "and origin"))

    # staleness vs the board file ------------------------------------------------
    board_bbox = ((getattr(pcb, "board", {}) or {}).get("outline_bbox")
                  if pcb is not None else None)
    if outline and board_bbox:
        s = geometry.unit_scale(pcb)
        (bx0, by0), (bx1, by1) = board_bbox
        bw, bh = abs(bx1 - bx0) * s, abs(by1 - by0) * s
        gw, gh = _size(outline.bbox_mm)
        if abs(gw - bw) > _STALE_TOL_MM or abs(gh - bh) > _STALE_TOL_MM:
            out.append(Finding(
                code="REVIEW_GERBER_STALE", severity=Severity.WARNING,
                message=(f"outline gerber is {gw:.1f}×{gh:.1f} mm but the "
                         f"board file measures {bw:.1f}×{bh:.1f} mm — the "
                         "export predates the last edit"),
                refs=[outline.name], confidence="deterministic",
                evidence={"source": "geometry",
                          "calc": {"gerber_mm": [round(gw, 2), round(gh, 2)],
                                   "board_mm": [round(bw, 2),
                                                round(bh, 2)]}},
                remediation="re-export the fab package before ordering"))
    return out


register(Detector(name="gerber.package", family="gerber", run=run,
                  rules=RULES))
