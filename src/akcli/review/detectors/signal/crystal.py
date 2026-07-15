"""Crystal load-capacitor review.

Every crystal should carry a symmetric pair of load capacitors, and the
effective load CL = C1·C2/(C1+C2) + C_stray should match the crystal's
specified CL (the datasheet comparison lands with the facts store; until
then the computed CL is an observation with the stray-capacitance assumption
stated). Cf. ST AN2867 §3.
"""

from __future__ import annotations

from ....report import Finding, Severity, anchor
from ... import Detector, Rule, register
from ... import topo
from ...tables import XTAL_CSTRAY_PF, XTAL_LOAD_TOL

RULES = (
    Rule(
        code="REVIEW_XTAL_NO_LOADCAPS",
        title="Crystal has no load capacitors",
        explain=(
            "Neither side of the crystal carries a capacitor to ground. "
            "Unless the oscillator IC integrates its load capacitance (some "
            "do — check the datasheet), the oscillator may not start or will "
            "run off-frequency."),
        default_severity="warning", confidence="heuristic", version="1",
        reference="ST AN2867 §3 (Pierce oscillator load capacitance)"),
    Rule(
        code="REVIEW_XTAL_ASYMMETRIC",
        title="Crystal load capacitors are asymmetric or one-sided",
        explain=(
            "The two crystal pins should see equal load capacitors; a missing "
            f"or >{XTAL_LOAD_TOL:.0%}-mismatched pair skews the oscillation "
            "point and degrades startup margin."),
        default_severity="warning", confidence="heuristic", version="1",
        reference="ST AN2867 §3 (Pierce oscillator load capacitance)"),
    Rule(
        code="REVIEW_XTAL_LOAD",
        title="Crystal effective load computed (verify against CL spec)",
        explain=(
            "CL = C1·C2/(C1+C2) + C_stray, with C_stray assumed "
            f"{XTAL_CSTRAY_PF} pF (typical board+pin figure, cf. ST AN2867 "
            "§3). With a facts file recording the crystal's specified "
            "load_capacitance the comparison is datasheet_backed; without "
            "one the computed CL is an observation to check by hand."),
        default_severity="info", confidence="heuristic", version="1",
        reference="ST AN2867 §3 (Pierce oscillator load capacitance)"),
    Rule(
        code="REVIEW_XTAL_LOAD_MISMATCH",
        title="Crystal load capacitors disagree with the datasheet CL",
        explain=(
            "The crystal's facts file records its specified load capacitance "
            "(pinned to the datasheet by sha256 + page), and the fitted "
            "pair computes to a CL more than 10 % away — the oscillator "
            "will run off-frequency or with degraded startup margin. The "
            "remediation suggests the cap value that hits the spec: "
            "C = 2·(CL − C_stray)."),
        default_severity="warning", confidence="datasheet_backed", version="1",
        reference="the part's facts file: load_capacitance + ST AN2867 §3"),
)

# CL specs are nominal and caps carry tolerance: 10 % comparison band.
_XTAL_SPEC_TOL = 0.10


def run(ctx: topo.ReviewCtx) -> list[Finding]:
    out: list[Finding] = []
    for comp in ctx.sch.components:
        if not topo.is_crystal(comp) or topo.is_power_symbol(comp):
            continue
        ref = comp.designator
        sides = [n for n in ctx.comp_nets.get(ref, [])
                 if not topo.net_is_ground(n) and not topo.net_is_power(n)]
        if len(sides) != 2:
            continue                     # oscillator module / shield-only: skip
        cap_sides = [topo.caps_to_ground(ctx, n) for n in sides]
        n_loaded = sum(1 for cs in cap_sides if cs)
        anchors = [anchor("component", ref)] + [anchor("net", n.name)
                                                for n in sides]
        if n_loaded == 0:
            out.append(Finding(
                code="REVIEW_XTAL_NO_LOADCAPS", severity=Severity.WARNING,
                message=(f"crystal {ref}: no load capacitors on "
                         f"{sides[0].name!r}/{sides[1].name!r}"),
                refs=[ref], anchors=anchors, confidence="heuristic",
                evidence={"source": "topology"},
                remediation=("add the load-cap pair per the crystal's CL "
                             "spec, or confirm the driver IC integrates its "
                             "load capacitance")))
            continue
        if n_loaded == 1:
            missing = sides[0] if not cap_sides[0] else sides[1]
            out.append(Finding(
                code="REVIEW_XTAL_ASYMMETRIC", severity=Severity.WARNING,
                message=(f"crystal {ref}: load capacitor missing on "
                         f"{missing.name!r} (one-sided load)"),
                refs=[ref], anchors=anchors, confidence="heuristic",
                evidence={"source": "topology"},
                remediation="fit the second load capacitor"))
            continue
        c1_ref, c2_ref = cap_sides[0][0], cap_sides[1][0]
        c1 = topo.parse_value(ctx.comps[c1_ref].value)
        c2 = topo.parse_value(ctx.comps[c2_ref].value)
        if c1 is None or c2 is None or c1 <= 0 or c2 <= 0:
            continue                     # unverifiable: silence over guesses
        if abs(c1 - c2) > XTAL_LOAD_TOL * max(c1, c2):
            out.append(Finding(
                code="REVIEW_XTAL_ASYMMETRIC", severity=Severity.WARNING,
                message=(f"crystal {ref}: asymmetric load caps "
                         f"{c1_ref}={ctx.comps[c1_ref].value} vs "
                         f"{c2_ref}={ctx.comps[c2_ref].value}"),
                refs=[ref, c1_ref, c2_ref], anchors=anchors,
                confidence="heuristic", evidence={"source": "topology"},
                remediation="make the load-cap pair equal"))
            continue
        cl_f = (c1 * c2) / (c1 + c2) + XTAL_CSTRAY_PF * 1e-12
        calc = {"formula": "CL = C1*C2/(C1+C2) + Cstray",
                "inputs": {"c1": c1, "c2": c2, "cstray_pf": XTAL_CSTRAY_PF},
                "results": {"cl_pf": round(cl_f * 1e12, 3)}}
        assumptions = [f"C_stray = {XTAL_CSTRAY_PF} pF "
                       "(board + pin, cf. ST AN2867 §3)"]
        cl_fact = ctx.fact_for(ref, "load_capacitance")
        spec = cl_fact.best() if cl_fact is not None else None
        if spec is not None and spec > 0:
            calc["inputs"]["cl_spec"] = spec
            ds_ev = {"source": "datasheet", "datasheet": cl_fact.evidence(),
                     "calc": calc, "assumptions": assumptions}
            if abs(cl_f - spec) > _XTAL_SPEC_TOL * spec:
                c_suggest = 2.0 * (spec - XTAL_CSTRAY_PF * 1e-12)
                out.append(Finding(
                    code="REVIEW_XTAL_LOAD_MISMATCH", severity=Severity.WARNING,
                    message=(f"crystal {ref}: fitted load computes to "
                             f"{cl_f * 1e12:.3g} pF but the datasheet "
                             f"specifies CL = {spec * 1e12:.3g} pF"),
                    refs=[ref, c1_ref, c2_ref], anchors=anchors,
                    confidence="datasheet_backed", evidence=ds_ev,
                    remediation=(f"fit C1 = C2 ≈ {c_suggest * 1e12:.3g} pF "
                                 "(C = 2·(CL − C_stray))"),
                    fix_params={"kind": "xtal_load_retune",
                                "c1": c1_ref, "c2": c2_ref,
                                "c_suggested_pf": round(c_suggest * 1e12, 2)}))
            else:
                out.append(Finding(
                    code="REVIEW_XTAL_LOAD", severity=Severity.INFO,
                    message=(f"crystal {ref}: effective load "
                             f"{cl_f * 1e12:.3g} pF matches the datasheet "
                             f"CL {spec * 1e12:.3g} pF"),
                    refs=[ref, c1_ref, c2_ref], anchors=anchors,
                    confidence="datasheet_backed", evidence=ds_ev))
            continue
        out.append(Finding(
            code="REVIEW_XTAL_LOAD", severity=Severity.INFO,
            message=(f"crystal {ref}: effective load CL≈{cl_f * 1e12:.3g} pF "
                     f"(C_stray {XTAL_CSTRAY_PF} pF assumed) — verify against "
                     "the crystal's CL spec"),
            refs=[ref, c1_ref, c2_ref], anchors=anchors,
            confidence="heuristic",
            evidence={"source": "topology", "calc": calc,
                      "assumptions": assumptions},
            remediation="compare CL with the crystal datasheet's specified "
                        "load capacitance"))
    return out


register(Detector(name="signal.crystal", family="signal", run=run,
                  rules=RULES))
