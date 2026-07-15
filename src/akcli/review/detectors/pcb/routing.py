"""Routing-completeness review: nets whose pads sit on disconnected copper.

The copper partition comes from the union-find in :mod:`...geometry`
(pads + tracks + vias; zones merge by bbox, so a zone-poured net can never
be a false positive). More than one pad-bearing island = the ratsnest still
has work; deterministic geometry, no heuristics involved.
"""

from __future__ import annotations

from ....report import Finding, Severity, anchor
from ... import Detector, Rule, register
from ... import geometry

_MAX_LISTED = 6

RULES = (
    Rule(
        code="REVIEW_PCB_UNROUTED",
        title="Net's pads sit on disconnected copper islands",
        explain=(
            "Union-find over the net's copper (pads, tracks, vias; zones "
            "merged by bounding box) leaves more than one island that "
            "contains pads — the net is not fully routed. Zone merging is "
            "conservative (a zone can only over-merge), so this is never a "
            "false positive from a poured plane; a spatially split zone can "
            "however mask a genuine gap, which the board house's DRC still "
            "catches."),
        default_severity="warning", confidence="deterministic", version="1",
        reference=None),
)


def run(ctx) -> list[Finding]:
    pcb = ctx.pcb
    if pcb is None:
        return []
    out: list[Finding] = []
    for net in sorted(n for n in getattr(pcb, "nets", []) or [] if n):
        pads_on_net = [p for p in getattr(pcb, "pads", []) or []
                       if p.get("net") == net]
        if len(pads_on_net) < 2:
            continue
        groups = geometry.net_islands(pcb, net).pad_groups()
        if len(groups) <= 1:
            continue
        sample = sorted(min((e.label for e in g)) for g in groups)
        shown = ", ".join(sample[:_MAX_LISTED]) + (
            f", … (+{len(sample) - _MAX_LISTED})"
            if len(sample) > _MAX_LISTED else "")
        out.append(Finding(
            code="REVIEW_PCB_UNROUTED", severity=Severity.WARNING,
            message=(f"net {net!r}: {len(pads_on_net)} pad(s) split across "
                     f"{len(groups)} copper islands (one per island: {shown})"),
            refs=[net],
            anchors=[anchor("net", net)]
                    + [anchor("pin", s) for s in sample[:_MAX_LISTED]],
            confidence="deterministic",
            evidence={"source": "geometry",
                      "calc": {"islands": len(groups),
                               "pads": len(pads_on_net)}},
            remediation="finish routing (or pour/repair the zone) so every "
                        "pad shares one copper island"))
    return out


register(Detector(name="pcb.routing", family="pcb", run=run, rules=RULES))
