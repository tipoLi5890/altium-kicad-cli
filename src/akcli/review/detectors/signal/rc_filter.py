"""RC low-pass observation: series R into a shunt C to ground.

The corner frequency itself comes from ``akcli calc rc`` — the calc envelope
(inputs, results, literature reference) rides in the finding's evidence
verbatim, so the number is re-computable and cited.
"""

from __future__ import annotations

from ....report import Finding, Severity, anchor
from ... import Detector, Rule, register
from ... import topo

RULES = (
    Rule(
        code="REVIEW_RC_CUTOFF",
        title="RC low-pass observed (computed −3 dB corner)",
        explain=(
            "A series resistor feeding a node with a shunt capacitor to "
            "ground forms a first-order low-pass; fc = 1/(2πRC) is computed "
            "via `akcli calc rc` and reported as an observation so a reviewer "
            "can spot a corner that contradicts the signal's intent (e.g. a "
            "100 Hz pole on an SPI line). Note a pull-up + decoupling pair "
            "matches the same shape — judge against the net's role."),
        default_severity="info", confidence="deterministic", version="1",
        reference="Horowitz & Hill, The Art of Electronics (via `akcli calc rc`)"),
)


def run(ctx: topo.ReviewCtx) -> list[Finding]:
    from ....calc import compute

    out: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for net in ctx.sch.nets:
        if topo.net_is_ground(net) or topo.net_is_power(net):
            continue
        caps = topo.caps_to_ground(ctx, net)
        if not caps:
            continue
        rs = sorted({ref for ref, _pin in net.members
                     if ref in ctx.comps and topo.is_resistor(ctx.comps[ref])
                     and topo.other_net(ctx, ref, net) is not None})
        for r_ref in rs:
            for c_ref in caps:
                key = (r_ref, c_ref)
                if key in seen:
                    continue
                seen.add(key)
                r = topo.parse_value(ctx.comps[r_ref].value)
                c = topo.parse_value(ctx.comps[c_ref].value)
                if r is None or c is None or r <= 0 or c <= 0:
                    continue        # unverifiable pair: stay silent, not wrong
                env = compute("rc", {"r": r, "c": c})
                fc = env["results"]["fc"]["value"]
                out.append(Finding(
                    code="REVIEW_RC_CUTOFF", severity=Severity.INFO,
                    message=(f"RC low-pass {r_ref}/{c_ref} on net "
                             f"{net.name!r}: fc = {fc:,.4g} Hz"),
                    refs=[r_ref, c_ref],
                    anchors=[anchor("component", r_ref),
                             anchor("component", c_ref),
                             anchor("net", net.name)],
                    confidence="deterministic",
                    evidence={"source": "calc", "calc": env},
                    remediation=("confirm the corner suits this net's "
                                 "bandwidth; retune R or C if not")))
    return out


register(Detector(name="signal.rc_filter", family="signal", run=run,
                  rules=RULES))
