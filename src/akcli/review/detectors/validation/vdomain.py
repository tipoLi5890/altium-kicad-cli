"""Cross-voltage-domain signal review (M3).

A signal net joining ICs powered from different rails (a 5 V driver into a
3.3 V input) is flagged for tolerance verification. A device's domain is
inferred from the power rails its pins touch — heuristic by construction;
the datasheet-backed "is this pin 5 V-tolerant" upgrade arrives with the
facts store (M4). Level shifters are legitimate cross-domain parts: they
touch BOTH rails and are therefore excluded automatically.
"""

from __future__ import annotations

from ....report import Finding, Severity, anchor
from ... import Detector, Rule, register
from ... import topo

# Rails closer than this are one domain (3.3 vs 3.0 is regulator tolerance,
# not a domain crossing).
_DOMAIN_DELTA_V = 0.6

RULES = (
    Rule(
        code="REVIEW_VDOMAIN_CROSS",
        title="Signal net crosses voltage domains",
        explain=(
            "This net joins ICs whose supply rails differ by more than "
            f"{_DOMAIN_DELTA_V} V — a higher-rail driver can overdrive a "
            "lower-rail input unless that input is rated tolerant. Domains "
            "are inferred from the power rails each IC touches; a part "
            "powered from BOTH rails (a level shifter) makes the net one "
            "domain and is not flagged. Verify the receiving pin's absolute "
            "maximum (datasheet_backed verification lands with the facts "
            "store), add a shifter/divider, or waive."),
        default_severity="warning", confidence="heuristic", version="1",
        reference="receiving pin's absolute-maximum rating vs driver swing"),
)


def _ic_rails(ctx: topo.ReviewCtx) -> dict[str, set[float]]:
    """``{designator: {rail volts}}`` for every IC (≥3 nets, not connector)."""
    rails: dict[str, set[float]] = {}
    for comp in ctx.sch.components:
        ref = comp.designator
        nets = ctx.comp_nets.get(ref, [])
        if (len(nets) < 3 or topo.is_power_symbol(comp)
                or topo.is_connector(comp) or topo.is_tvs(comp)):
            continue
        vs = set()
        for n in nets:
            if topo.net_is_ground(n):
                continue
            v = topo.net_implied_voltage(n)
            if v is not None and (topo.net_is_power(n)):
                vs.add(v)
        if vs:
            rails[ref] = vs
    return rails


def run(ctx: topo.ReviewCtx) -> list[Finding]:
    out: list[Finding] = []
    rails = _ic_rails(ctx)
    for net in ctx.sch.nets:
        if topo.net_is_ground(net) or topo.net_is_power(net) \
                or topo.net_implied_voltage(net) is not None:
            continue                       # rails themselves are not signals
        domains: dict[str, set[float]] = {}
        for ref, _pin in net.members:
            if ref in rails:
                domains[ref] = rails[ref]
        if len(domains) < 2:
            continue
        # a part living in both extremes bridges the domains (level shifter)
        lo = min(min(v) for v in domains.values())
        hi = max(max(v) for v in domains.values())
        if hi - lo <= _DOMAIN_DELTA_V:
            continue
        if any(min(v) <= lo + 1e-9 and max(v) >= hi - 1e-9
               for v in domains.values()):
            continue
        parts = ", ".join(f"{r}({'/'.join(f'{v:g}V' for v in sorted(vs))})"
                          for r, vs in sorted(domains.items()))
        base = dict(
            refs=[net.name] + sorted(domains),
            anchors=[anchor("net", net.name)]
                    + [anchor("component", r) for r in sorted(domains)])

        # datasheet-backed adjudication: the lower-domain ICs' abs_max_io
        low_refs = sorted(r for r, vs in domains.items()
                          if max(vs) < hi - 1e-9)
        facts = {r: ctx.fact_for(r, "abs_max_io") for r in low_refs}
        violated = [(r, f) for r, f in facts.items()
                    if f is not None and (f.best() or 0) < hi]
        if violated:
            r, f = violated[0]
            out.append(Finding(
                code="REVIEW_VDOMAIN_CROSS", severity=Severity.WARNING,
                message=(f"net {net.name!r}: {r}'s datasheet absolute "
                         f"maximum is {f.best():g} V but the {hi:g} V domain "
                         f"drives this net ({parts})"),
                confidence="datasheet_backed",
                evidence={"source": "datasheet", "datasheet": f.evidence()},
                remediation=("add a level shifter/divider — the receiving "
                             "pin is NOT tolerant per its datasheet"),
                **base))
            continue
        if low_refs and all(f is not None and (f.best() or 0) >= hi
                            for f in facts.values()):
            f = facts[low_refs[0]]
            out.append(Finding(
                code="REVIEW_VDOMAIN_CROSS", severity=Severity.INFO,
                message=(f"net {net.name!r} crosses domains ({parts}) but "
                         f"every receiving pin is rated ≥ {hi:g} V per its "
                         "datasheet — verified tolerant"),
                confidence="datasheet_backed",
                evidence={"source": "datasheet", "datasheet": f.evidence()},
                **base))
            continue
        out.append(Finding(
            code="REVIEW_VDOMAIN_CROSS", severity=Severity.WARNING,
            message=(f"net {net.name!r} joins ICs on different rails: "
                     f"{parts} — verify input tolerance"),
            confidence="heuristic", evidence={"source": "topology"},
            remediation=("check the lower-rail pin's absolute maximum, add "
                         "a level shifter/divider, or waive if tolerant"),
            **base))
    return out


register(Detector(name="validation.vdomain", family="validation", run=run,
                  rules=RULES))
