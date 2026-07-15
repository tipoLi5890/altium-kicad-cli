"""Differential-pair intra-pair skew review (EMC batch 2).

Skew converts differential energy into common mode — the strongest radiator
on the board. Pair discovery is by net-name convention (_P/_N, +/−,
_DP/_DM); the length is the sum of the pair's track segments, so a fully
unrouted side stays with the routing rule, not this one.
"""

from __future__ import annotations

from ....report import Finding, Severity, anchor
from ... import Detector, Rule, register
from ... import geometry
from ...tables import EMC_DIFF_SKEW_PS, EMC_PS_PER_MM

_SUFFIXES = (("_P", "_N"), ("_DP", "_DM"), ("+", "-"))

RULES = (
    Rule(
        code="REVIEW_EMC_DIFFPAIR_SKEW",
        title="Differential pair's sides differ in routed length",
        explain=(
            "Intra-pair skew beyond "
            f"{EMC_DIFF_SKEW_PS:g} ps (at ≈{EMC_PS_PER_MM:g} ps/mm on FR4 "
            "microstrip — assumption stated) converts differential signal "
            "into common-mode current, the dominant cable/board radiator. "
            "Lengths are summed per net over all segments; serpentine the "
            "short side at the mismatch point."),
        default_severity="warning", confidence="heuristic", version="1",
        reference="common-mode conversion from intra-pair skew (~25 ps "
                  "budget for high-speed pairs)"),
)


def _net_length_mm(pcb, net: str) -> float:
    s = geometry.unit_scale(pcb)
    total = 0.0
    for t in getattr(pcb, "tracks", []) or []:
        if t.get("net") != net:
            continue
        (x1, y1), (x2, y2) = t.get("start"), t.get("end")
        total += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 * s
    return total


def _pairs(nets) -> list[tuple[str, str]]:
    names = set(nets)
    out = []
    for name in sorted(names):
        for suf_p, suf_n in _SUFFIXES:
            if name.endswith(suf_p):
                partner = name[: -len(suf_p)] + suf_n
                if partner in names:
                    out.append((name, partner))
                break
    return out


def run(ctx) -> list[Finding]:
    pcb = ctx.pcb
    if pcb is None:
        return []
    out: list[Finding] = []
    for pos, neg in _pairs(n for n in getattr(pcb, "nets", []) or [] if n):
        lp = _net_length_mm(pcb, pos)
        ln = _net_length_mm(pcb, neg)
        if lp <= 0 or ln <= 0:
            continue                 # unrouted side: the routing rule's job
        skew_mm = abs(lp - ln)
        skew_ps = skew_mm * EMC_PS_PER_MM
        if skew_ps <= EMC_DIFF_SKEW_PS:
            continue
        out.append(Finding(
            code="REVIEW_EMC_DIFFPAIR_SKEW", severity=Severity.WARNING,
            message=(f"pair {pos!r}/{neg!r}: {skew_mm:.2f} mm length "
                     f"mismatch ≈ {skew_ps:.0f} ps skew (budget "
                     f"{EMC_DIFF_SKEW_PS:g} ps)"),
            refs=[pos, neg],
            anchors=[anchor("net", pos), anchor("net", neg)],
            confidence="heuristic",
            evidence={"source": "geometry",
                      "calc": {"len_p_mm": round(lp, 2),
                               "len_n_mm": round(ln, 2),
                               "skew_ps": round(skew_ps, 1),
                               "budget_ps": EMC_DIFF_SKEW_PS},
                      "assumptions": [
                          f"{EMC_PS_PER_MM:g} ps/mm (FR4 microstrip)"]},
            remediation="length-match the pair at the point of mismatch",
            fix_params={"kind": "diffpair_match", "short_side":
                        pos if lp < ln else neg,
                        "add_mm": round(skew_mm, 2)}))
    return out


register(Detector(name="emc.diffpair", family="emc", run=run, rules=RULES))
