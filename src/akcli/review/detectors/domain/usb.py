"""USB-C CC termination review (M8, first domain family).

A USB-C sink advertises itself with Rd = 5.1 kΩ from each CC pin to ground
(USB Type-C spec §4.5.1.2); without it, a host port supplies no VBUS and
"the board doesn't power up over half the cables" is the classic symptom.
A CC net that reaches an IC is assumed to be handled by a USB-C controller
(they integrate Rd) and is skipped — stated, not guessed.
"""

from __future__ import annotations

from ....report import Finding, Severity, anchor
from ... import Detector, Rule, register
from ... import topo

_RD_OHMS = 5100.0
_RD_TOL = 0.10

RULES = (
    Rule(
        code="REVIEW_USB_CC_MISSING",
        title="USB-C CC pin has no Rd pull-down",
        explain=(
            "A CC1/CC2 pin's net carries no resistor to ground and no IC "
            "that could integrate the termination. A sink must present "
            f"Rd = {_RD_OHMS / 1000:g} kΩ on each CC pin or a source port "
            "never enables VBUS — the board appears dead on exactly half "
            "of the cable orientations that reach it."),
        default_severity="warning", confidence="heuristic", version="1",
        reference="USB Type-C spec §4.5.1.2: Rd = 5.1 kΩ ±10 % (sink)"),
    Rule(
        code="REVIEW_USB_CC_VALUE",
        title="USB-C CC pull-down is not 5.1 kΩ",
        explain=(
            "The CC pull-down differs from Rd = 5.1 kΩ by more than "
            f"{_RD_TOL:.0%}: the advertised device class is wrong or "
            "undefined, and current negotiation misbehaves."),
        default_severity="warning", confidence="heuristic", version="1",
        reference="USB Type-C spec §4.5.1.2: Rd = 5.1 kΩ ±10 % (sink)"),
)


def run(ctx: topo.ReviewCtx) -> list[Finding]:
    out: list[Finding] = []
    for comp in ctx.sch.components:
        if not topo.is_connector(comp) or topo.is_power_symbol(comp):
            continue
        ref = comp.designator
        cc_pins = [p for p in comp.pins
                   if (p.name or "").strip().upper() in ("CC1", "CC2", "CC")]
        for pin in cc_pins:
            net = ctx.net_of.get((ref, str(pin.number)))
            if net is None:
                continue
            # a USB-C controller on the net integrates Rd: out of scope
            if any(len(ctx.comp_nets.get(r, [])) >= 3
                   for r, _p in net.members
                   if r != ref and r in ctx.comps
                   and not topo.is_power_symbol(ctx.comps[r])):
                continue
            pulls = [r for r, _p in net.members
                     if r in ctx.comps and topo.is_resistor(ctx.comps[r])
                     and (lambda on: on is not None
                          and topo.net_is_ground(on))(
                              topo.other_net(ctx, r, net))]
            anchors = [anchor("component", ref),
                       anchor("pin", f"{ref}.{pin.number}"),
                       anchor("net", net.name)]
            if not pulls:
                out.append(Finding(
                    code="REVIEW_USB_CC_MISSING", severity=Severity.WARNING,
                    message=(f"{ref}.{pin.number} ({pin.name}) on net "
                             f"{net.name!r} has no Rd pull-down — a source "
                             "port will not enable VBUS"),
                    refs=[ref, net.name], anchors=anchors,
                    confidence="heuristic",
                    evidence={"source": "topology"},
                    remediation=(f"fit Rd = 5.1 kΩ from {pin.name} to GND, "
                                 "or waive if a USB-C controller handles CC "
                                 "elsewhere"),
                    fix_params={"kind": "add_pullup", "net": net.name}))
                continue
            r_ref = sorted(pulls)[0]
            r = topo.parse_value(ctx.comps[r_ref].value)
            if r is None:
                continue                    # unverifiable value: no guess
            if abs(r - _RD_OHMS) > _RD_TOL * _RD_OHMS:
                out.append(Finding(
                    code="REVIEW_USB_CC_VALUE", severity=Severity.WARNING,
                    message=(f"{ref}.{pin.number} ({pin.name}): pull-down "
                             f"{r_ref}={ctx.comps[r_ref].value} is not "
                             f"Rd = 5.1 kΩ ±{_RD_TOL:.0%}"),
                    refs=[ref, r_ref], anchors=anchors,
                    confidence="heuristic",
                    evidence={"source": "topology",
                              "calc": {"measured_ohms": r,
                                       "rd_ohms": _RD_OHMS,
                                       "tol": _RD_TOL}},
                    remediation=f"set {r_ref} to 5.1k",
                    fix_params={"kind": "retune_pullup", "ref": r_ref}))
    return out


register(Detector(name="domain.usb", family="domain", run=run, rules=RULES))
