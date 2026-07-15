"""Voltage-divider review: feedback dividers and named taps.

Recognises rail→R→tap→R→ground chains, computes the ratio, and judges
plausibility. The ratio math is deterministic; anything that leans on a
NAME-implied voltage is honestly ``heuristic``.
"""

from __future__ import annotations

from ....report import Finding, Severity, anchor
from ... import Detector, Rule, register
from ... import topo
from ...tables import DIVIDER_TAP_TOL, VREF_PLAUSIBLE_V

RULES = (
    Rule(
        code="REVIEW_FB_DIVIDER",
        title="Feedback divider observed (computed implied Vref)",
        explain=(
            "A rail→R_top→FB→R_bottom→GND chain feeds an IC feedback/sense "
            "pin. For the standard topology Vout = Vref·(1 + R_top/R_bottom), "
            "so the implied reference is Vref = Vout·R_bottom/(R_top+R_bottom) "
            "with Vout taken from the rail name. Reported as an observation; "
            "verify Vref against the regulator datasheet (datasheet_backed "
            "verification lands with the facts store)."),
        default_severity="info", confidence="heuristic", version="1",
        reference="standard regulator topology: Vout = Vref·(1 + Rt/Rb)"),
    Rule(
        code="REVIEW_FB_DIVIDER_VREF",
        title="Feedback divider implies an implausible reference voltage",
        explain=(
            "The implied Vref = Vout·R_bottom/(R_top+R_bottom) falls outside "
            f"the plausible reference band {VREF_PLAUSIBLE_V} V. Real "
            "regulator references cluster in 0.5–1.25 V (up to 2.5 V for "
            "shunt references) — an implied Vref outside the band usually "
            "means R_top/R_bottom are swapped or mis-valued, producing a "
            "wrong output voltage."),
        default_severity="warning", confidence="heuristic", version="1",
        reference="typical bandgap references: 0.5–1.25 V (up to 2.5 V shunt)"),
    Rule(
        code="REVIEW_DIVIDER_TAP_MISMATCH",
        title="Divider tap voltage disagrees with the tap net's name",
        explain=(
            "The tap of a rail→R→tap→R→GND divider computes to "
            "V_tap = V_rail·R_bottom/(R_top+R_bottom), but the tap NET NAME "
            f"implies a different voltage (>{DIVIDER_TAP_TOL:.0%} off). "
            "Either the resistor values or the net name is wrong — both "
            "mislead the next reader."),
        default_severity="warning", confidence="heuristic", version="1",
        reference=None),
    Rule(
        code="REVIEW_DIVIDER_UNVALUED",
        title="Divider resistor value does not parse",
        explain=(
            "A recognised divider carries a resistor whose Value field cannot "
            "be parsed as a resistance, so the ratio cannot be verified. "
            "Reported as insufficient_evidence — the review never guesses a "
            "value."),
        default_severity="note", confidence="deterministic", version="1",
        reference=None),
    Rule(
        code="REVIEW_FB_DIVIDER_VREF_MISMATCH",
        title="Feedback divider disagrees with the datasheet Vref",
        explain=(
            "The regulator's facts file records its reference voltage "
            "(pinned to the datasheet PDF by sha256 + page). The divider "
            "implies Vref = Vout·R_b/(R_t+R_b) from the output rail's name, "
            "and it differs from the recorded Vref by more than 5 % — the "
            "output voltage will not be what the rail name promises. This is "
            "a datasheet_backed judgement; the evidence block carries the "
            "exact page."),
        default_severity="warning", confidence="datasheet_backed", version="1",
        reference="the part's facts file: vref (datasheets/extracted/)"),
)


def _evidence(formula: str, inputs: dict, results: dict) -> dict:
    return {"source": "topology",
            "calc": {"formula": formula, "inputs": inputs, "results": results}}


def _anchors(d: topo.Divider) -> list:
    return [anchor("component", d.r_top), anchor("component", d.r_bottom),
            anchor("net", d.mid.name)]


def run(ctx: topo.ReviewCtx) -> list[Finding]:
    out: list[Finding] = []
    for d in topo.find_dividers(ctx):
        fb = topo.fb_pin_on(ctx, d.mid)
        if fb is None and not d.powered:
            continue    # plain divider between arbitrary signals: not reviewed
        rt = topo.parse_value(ctx.comps[d.r_top].value)
        rb = topo.parse_value(ctx.comps[d.r_bottom].value)
        if rt is None or rb is None or (rt + rb) <= 0:
            bad = [r for r, v in ((d.r_top, rt), (d.r_bottom, rb)) if v is None]
            out.append(Finding(
                code="REVIEW_DIVIDER_UNVALUED", severity=Severity.NOTE,
                message=(f"divider {d.r_top}/{d.r_bottom} on net "
                         f"{d.mid.name!r}: unparseable value on "
                         f"{', '.join(bad) or 'resistors'} — ratio unverifiable"),
                refs=[d.r_top, d.r_bottom], anchors=_anchors(d),
                confidence="deterministic", status="insufficient_evidence",
                evidence={"source": "topology"}))
            continue
        ratio = rb / (rt + rb)
        vtop = topo.net_implied_voltage(d.top)
        if fb is not None:
            ref, pin = fb
            # datasheet-backed path: a recorded Vref beats every heuristic
            vref_fact = ctx.fact_for(ref, "vref")
            spec = vref_fact.best() if vref_fact is not None else None
            if spec is not None and spec > 0:
                ds_ev = {"source": "datasheet",
                         "datasheet": vref_fact.evidence()}
                if vtop is not None:
                    implied = vtop * ratio
                    calc = {"formula": "Vref = Vout*Rb/(Rt+Rb)",
                            "inputs": {"r_top": rt, "r_bottom": rb,
                                       "vout_from_rail": vtop,
                                       "vref_spec": spec},
                            "results": {"implied_vref": round(implied, 4)}}
                    if abs(implied - spec) > 0.05 * spec:
                        vout_real = spec * (rt + rb) / rb
                        out.append(Finding(
                            code="REVIEW_FB_DIVIDER_VREF_MISMATCH",
                            severity=Severity.WARNING,
                            message=(f"{ref}.{pin} feedback divider "
                                     f"{d.r_top}/{d.r_bottom} implies Vref="
                                     f"{implied:.3g} V but the datasheet "
                                     f"records {spec:.3g} V — the rail "
                                     f"{d.top.name!r} will actually sit at "
                                     f"{vout_real:.3g} V"),
                            refs=[ref, d.r_top, d.r_bottom],
                            anchors=_anchors(d) + [anchor("pin", f"{ref}.{pin}")],
                            confidence="datasheet_backed",
                            evidence={**ds_ev, "calc": calc},
                            remediation=(f"retune the divider for Vref="
                                         f"{spec:.3g} V (or fix the rail "
                                         "name)"),
                            fix_params={"kind": "fb_divider_retune",
                                        "r_top": d.r_top, "r_bottom": d.r_bottom,
                                        "vref_spec": spec,
                                        "vout_actual": round(vout_real, 4)}))
                    else:
                        out.append(Finding(
                            code="REVIEW_FB_DIVIDER", severity=Severity.INFO,
                            message=(f"{ref}.{pin} feedback divider "
                                     f"{d.r_top}/{d.r_bottom} matches the "
                                     f"datasheet Vref {spec:.3g} V for rail "
                                     f"{d.top.name!r}"),
                            refs=[ref, d.r_top, d.r_bottom],
                            anchors=_anchors(d) + [anchor("pin", f"{ref}.{pin}")],
                            confidence="datasheet_backed",
                            evidence={**ds_ev, "calc": calc}))
                else:
                    vout = spec * (rt + rb) / rb
                    out.append(Finding(
                        code="REVIEW_FB_DIVIDER", severity=Severity.INFO,
                        message=(f"{ref}.{pin} feedback divider "
                                 f"{d.r_top}/{d.r_bottom}: datasheet Vref "
                                 f"{spec:.3g} V sets Vout = {vout:.3g} V on "
                                 f"{d.top.name!r}"),
                        refs=[ref, d.r_top, d.r_bottom],
                        anchors=_anchors(d) + [anchor("pin", f"{ref}.{pin}")],
                        confidence="datasheet_backed",
                        evidence={**ds_ev,
                                  "calc": {"formula": "Vout = Vref*(Rt+Rb)/Rb",
                                           "inputs": {"r_top": rt,
                                                      "r_bottom": rb,
                                                      "vref_spec": spec},
                                           "results": {"vout": round(vout, 4)}}}))
                continue
            if vtop is not None:
                vref = vtop * ratio
                inputs = {"r_top": rt, "r_bottom": rb, "vout_from_rail": vtop}
                results = {"implied_vref": round(vref, 4), "ratio": round(ratio, 6)}
                lo, hi = VREF_PLAUSIBLE_V
                if not (lo <= vref <= hi):
                    out.append(Finding(
                        code="REVIEW_FB_DIVIDER_VREF", severity=Severity.WARNING,
                        message=(f"{ref}.{pin} feedback divider "
                                 f"{d.r_top}/{d.r_bottom} implies Vref="
                                 f"{vref:.3g} V from rail {d.top.name!r} — "
                                 f"outside the plausible band {lo}–{hi} V "
                                 "(swapped or mis-valued resistors?)"),
                        refs=[ref, d.r_top, d.r_bottom],
                        anchors=_anchors(d) + [anchor("pin", f"{ref}.{pin}")],
                        confidence="heuristic",
                        evidence=_evidence("Vref = Vout*Rb/(Rt+Rb)", inputs, results),
                        remediation=(f"check R_top={ctx.comps[d.r_top].value} / "
                                     f"R_bottom={ctx.comps[d.r_bottom].value} "
                                     "against the regulator's datasheet Vref"),
                        fix_params={"kind": "fb_divider", "r_top": d.r_top,
                                    "r_bottom": d.r_bottom,
                                    "implied_vref": round(vref, 4)}))
                else:
                    out.append(Finding(
                        code="REVIEW_FB_DIVIDER", severity=Severity.INFO,
                        message=(f"{ref}.{pin} feedback divider "
                                 f"{d.r_top}/{d.r_bottom}: rail "
                                 f"{d.top.name!r} implies Vref={vref:.3g} V "
                                 "(verify against the datasheet)"),
                        refs=[ref, d.r_top, d.r_bottom],
                        anchors=_anchors(d) + [anchor("pin", f"{ref}.{pin}")],
                        confidence="heuristic",
                        evidence=_evidence("Vref = Vout*Rb/(Rt+Rb)", inputs, results),
                        remediation="confirm Vref in the regulator datasheet"))
            else:
                out.append(Finding(
                    code="REVIEW_FB_DIVIDER", severity=Severity.INFO,
                    message=(f"{ref}.{pin} feedback divider "
                             f"{d.r_top}/{d.r_bottom}: ratio Rb/(Rt+Rb)="
                             f"{ratio:.4g}; rail voltage unknown, so "
                             "Vout = Vref/(ratio) once Vref is known"),
                    refs=[ref, d.r_top, d.r_bottom],
                    anchors=_anchors(d) + [anchor("pin", f"{ref}.{pin}")],
                    confidence="deterministic", status="insufficient_evidence",
                    evidence=_evidence("ratio = Rb/(Rt+Rb)",
                                       {"r_top": rt, "r_bottom": rb},
                                       {"ratio": round(ratio, 6)})))
            continue
        # plain divider: computed tap vs the tap net's own implied name
        vmid_named = topo.net_implied_voltage(d.mid)
        if vtop is not None and vmid_named is not None:
            vmid = vtop * ratio
            if abs(vmid - vmid_named) > DIVIDER_TAP_TOL * max(vmid_named, 1e-9):
                out.append(Finding(
                    code="REVIEW_DIVIDER_TAP_MISMATCH", severity=Severity.WARNING,
                    message=(f"divider {d.r_top}/{d.r_bottom}: tap "
                             f"{d.mid.name!r} computes to {vmid:.3g} V from "
                             f"rail {d.top.name!r}, but its name implies "
                             f"{vmid_named:.3g} V"),
                    refs=[d.r_top, d.r_bottom], anchors=_anchors(d),
                    confidence="heuristic",
                    evidence=_evidence(
                        "V_tap = V_rail*Rb/(Rt+Rb)",
                        {"r_top": rt, "r_bottom": rb, "v_rail": vtop},
                        {"v_tap": round(vmid, 4),
                         "v_named": vmid_named}),
                    remediation=("fix the resistor values or rename the tap "
                                 "net to the real voltage"),
                    fix_params={"kind": "divider_tap", "r_top": d.r_top,
                                "r_bottom": d.r_bottom,
                                "v_computed": round(vmid, 4),
                                "v_named": vmid_named}))
    return out


register(Detector(name="signal.divider", family="signal", run=run, rules=RULES))
