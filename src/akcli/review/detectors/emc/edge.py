"""Board-edge routing review (EMC batches 1–2).

Fields fringe past the plane edge: a track hugging the outline radiates (and
receives ESD) far better than one over solid copper. A CLOCK doing it is
worse — periodic content concentrates the spectrum. Needs the board outline;
without an Edge.Cuts bbox both rules stay silent (insufficient geometry, not
a pass).
"""

from __future__ import annotations

import re

from ....report import Finding, Severity, anchor
from ... import Detector, Rule, register
from ... import geometry
from ...tables import CLOCK_NET_TOKENS, EMC_EDGE_MARGIN_MM

_MAX_LISTED = 6
_CLOCK_RX = re.compile(
    r"(^|[_./])(" + "|".join(CLOCK_NET_TOKENS) + r")\d*([_./]|$)",
    re.IGNORECASE)

RULES = (
    Rule(
        code="REVIEW_EMC_EDGE_TRACK",
        title="Signal routed along the board edge",
        explain=(
            "Track copper within "
            f"{EMC_EDGE_MARGIN_MM:g} mm of the outline (rectangular "
            "bounding-box approximation, stated): fringing fields radiate "
            "past the plane edge and the trace is first in line for edge "
            "ESD. Keep signals a couple of trace-widths inside the pour."),
        default_severity="note", confidence="heuristic", version="1",
        reference="plane-edge fringing / 20H-style guidance"),
    Rule(
        code="REVIEW_EMC_CLOCK_EDGE",
        title="Clock net routed along the board edge",
        explain=(
            "A clock-named net (token match: "
            + ", ".join(CLOCK_NET_TOKENS) +
            ") runs within the edge margin. Periodic signals put all their "
            "energy into harmonics — an edge-routed clock is the classic "
            "single-frequency emissions failure. Route clocks over solid "
            "plane, away from the outline."),
        default_severity="warning", confidence="heuristic", version="1",
        reference="clock harmonics vs radiated-emission limits"),
)


def _outline_mm(pcb):
    board = getattr(pcb, "board", {}) or {}
    bbox = board.get("outline_bbox")
    if not bbox:
        return None
    s = geometry.unit_scale(pcb)
    (x0, y0), (x1, y1) = bbox
    return (min(x0, x1) * s, min(y0, y1) * s,
            max(x0, x1) * s, max(y0, y1) * s)


def run(ctx) -> list[Finding]:
    pcb = ctx.pcb
    if pcb is None:
        return []
    outline = _outline_mm(pcb)
    if outline is None:
        return []                    # no Edge.Cuts: silent, not a pass
    x0, y0, x1, y1 = outline
    s = geometry.unit_scale(pcb)
    near: dict[str, float] = {}
    for t in getattr(pcb, "tracks", []) or []:
        net = t.get("net")
        if not net:
            continue
        for px, py in (t.get("start"), t.get("end")):
            d = min(px * s - x0, x1 - px * s, py * s - y0, y1 - py * s)
            if d < EMC_EDGE_MARGIN_MM:
                near[net] = min(near.get(net, d), d)
    out: list[Finding] = []
    clocks = sorted(n for n in near if _CLOCK_RX.search(n))
    plain = sorted(n for n in near if n not in clocks)
    assumptions = ["rectangular-outline approximation (Edge.Cuts bbox)",
                   f"edge margin {EMC_EDGE_MARGIN_MM:g} mm"]
    for net in clocks:
        out.append(Finding(
            code="REVIEW_EMC_CLOCK_EDGE", severity=Severity.WARNING,
            message=(f"clock net {net!r} runs {near[net]:.2f} mm from the "
                     "board edge"),
            refs=[net], anchors=[anchor("net", net)], confidence="heuristic",
            evidence={"source": "geometry",
                      "calc": {"distance_mm": round(near[net], 2)},
                      "assumptions": assumptions},
            remediation="pull the clock inboard over solid plane"))
    if plain:
        shown = ", ".join(plain[:_MAX_LISTED]) + (
            f", … (+{len(plain) - _MAX_LISTED})"
            if len(plain) > _MAX_LISTED else "")
        out.append(Finding(
            code="REVIEW_EMC_EDGE_TRACK", severity=Severity.NOTE,
            message=(f"{len(plain)} net(s) routed within "
                     f"{EMC_EDGE_MARGIN_MM:g} mm of the board edge: {shown}"),
            refs=plain[:_MAX_LISTED],
            anchors=[anchor("net", n) for n in plain[:_MAX_LISTED]],
            confidence="heuristic",
            evidence={"source": "geometry", "assumptions": assumptions},
            remediation="keep signals a couple of trace-widths inside the "
                        "pour edge"))
    return out


register(Detector(name="emc.edge", family="emc", run=run, rules=RULES))
