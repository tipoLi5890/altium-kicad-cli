"""``review tree`` — the schematic's power structure, rail by rail (M7).

Built from the same topology primitives the detectors use: rails are
power-recognised nets; a rail's REGULATOR is the IC whose feedback divider
hangs off it (found via the divider/FB-pin recognisers); consumers are the
other ICs on the rail; decoupling is the rail's cap-to-ground count. Output
is deterministic (rails sorted by voltage then name) for diffing.
"""

from __future__ import annotations

from ..model import Schematic
from . import topo


def power_tree(sch: Schematic) -> dict:
    """``{"rails": [...]}`` — one entry per power-recognised net."""
    ctx = topo.build_ctx(sch)
    regulators: dict[str, dict] = {}
    for d in topo.find_dividers(ctx):
        fb = topo.fb_pin_on(ctx, d.mid)
        if fb is None:
            continue
        ref, pin = fb
        regulators.setdefault(d.top.stable_id, {
            "ref": ref, "fb_pin": f"{ref}.{pin}",
            "divider": [d.r_top, d.r_bottom]})

    rails = []
    for net in ctx.sch.nets:
        if topo.net_is_ground(net):
            continue
        voltage = topo.net_implied_voltage(net)
        if not topo.net_is_power(net) and voltage is None:
            continue
        reg = regulators.get(net.stable_id)
        consumers = sorted({
            ref for ref, _pin in net.members
            if ref in ctx.comps
            and len(ctx.comp_nets.get(ref, [])) >= 3
            and not topo.is_power_symbol(ctx.comps[ref])
            and (reg is None or ref != reg["ref"])})
        rails.append({
            "net": net.name,
            "voltage": voltage,
            "regulator": reg,
            "consumers": consumers,
            "decoupling_caps": len(topo.caps_to_ground(ctx, net)),
            "pins": len(net.members),
        })
    rails.sort(key=lambda r: (-(r["voltage"] or 0.0), r["net"]))
    return {"rails": rails}


def render_text(doc: dict) -> str:
    lines: list[str] = []
    rails = doc.get("rails", [])
    if not rails:
        return "power tree: no power-recognised rails\n"
    for r in rails:
        v = f"{r['voltage']:g} V" if r.get("voltage") is not None else "? V"
        lines.append(f"{r['net']}  ({v}, {r['pins']} pins, "
                     f"{r['decoupling_caps']} decoupling cap(s))")
        reg = r.get("regulator")
        if reg:
            lines.append(f"  ├─ regulated by {reg['ref']} "
                         f"(FB {reg['fb_pin']}, divider "
                         f"{'/'.join(reg['divider'])})")
        cons = r.get("consumers") or []
        for i, ref in enumerate(cons):
            branch = "└─" if i == len(cons) - 1 else "├─"
            lines.append(f"  {branch} {ref}")
        if not cons and not reg:
            lines.append("  └─ (no ICs on this rail)")
    return "\n".join(lines) + "\n"
