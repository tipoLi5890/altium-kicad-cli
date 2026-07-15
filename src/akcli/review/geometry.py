"""PCB copper geometry for the review layer (M5).

Works on the :class:`~..model.Pcb` dict primitives (pads / tracks / vias /
zones) in their native frame, normalised to **mm** via the board's declared
units (KiCad: mm; Altium: mil). The core is a per-net union-find over copper
elements — two elements join when they share a copper layer (or either spans
all of them) AND geometrically touch — giving the island partition that the
routing-completeness rule reads. Zones are merged by bbox (conservative: a
zone may over-merge, never under-merge, so an "unrouted" verdict stays a
true positive).
"""

from __future__ import annotations

from dataclasses import dataclass, field

_EPS_MM = 0.01
_OZ_MM = 0.035            # 1 oz copper thickness


def unit_scale(pcb) -> float:
    """mm per model unit (KiCad boards: 1.0; Altium boards store mils)."""
    units = (getattr(pcb, "board", {}) or {}).get("units")
    if units == "mil" or (units is None
                          and getattr(pcb, "source_format", "") == "altium"):
        return 0.0254
    return 1.0


# --------------------------------------------------------------------------- #
# copper elements
# --------------------------------------------------------------------------- #
@dataclass
class Element:
    """One copper element in mm: a pad, a track segment, or a via."""

    kind: str                     # pad | track | via
    index: int                    # index into the pcb's source list
    points: list[tuple[float, float]]
    radius: float                 # touch radius around each point / segment
    layers: frozenset[str] = frozenset()
    universal: bool = False       # spans every copper layer (thru pad / via)
    net: str | None = None
    label: str = ""


def _copper_layers(layers: list) -> tuple[frozenset[str], bool]:
    cu = frozenset(str(ln) for ln in layers or [] if str(ln).endswith(".Cu"))
    return cu, "*.Cu" in cu


def net_elements(pcb, net: str) -> list[Element]:
    """Every copper element bound to ``net``, coordinates in mm."""
    s = unit_scale(pcb)
    out: list[Element] = []
    for i, p in enumerate(getattr(pcb, "pads", []) or []):
        if p.get("net") != net:
            continue
        cu, star = _copper_layers(p.get("layers"))
        sx, sy = (p.get("size") or (0.0, 0.0))
        x, y = (p.get("at") or (0.0, 0.0))
        out.append(Element(
            kind="pad", index=i, points=[(x * s, y * s)],
            radius=max(float(sx or 0), float(sy or 0)) * s / 2.0,
            layers=cu,
            universal=star or p.get("pad_type") == "thru_hole",
            net=net, label=f"{p.get('component', '?')}.{p.get('number', '?')}"))
    for i, t in enumerate(getattr(pcb, "tracks", []) or []):
        if t.get("net") != net:
            continue
        (x1, y1), (x2, y2) = t.get("start") or (0, 0), t.get("end") or (0, 0)
        out.append(Element(
            kind="track", index=i,
            points=[(x1 * s, y1 * s), (x2 * s, y2 * s)],
            radius=float(t.get("width") or 0) * s / 2.0,
            layers=frozenset({str(t.get("layer"))}), net=net,
            label=f"track[{i}]"))
    for i, v in enumerate(getattr(pcb, "vias", []) or []):
        if v.get("net") != net:
            continue
        x, y = v.get("at") or (0, 0)
        cu, star = _copper_layers(v.get("layers"))
        out.append(Element(
            kind="via", index=i, points=[(x * s, y * s)],
            radius=float(v.get("size") or 0) * s / 2.0,
            layers=cu, universal=star or v.get("type") == "through" or not cu,
            net=net, label=f"via[{i}]"))
    return out


def _layers_touch(a: Element, b: Element) -> bool:
    return a.universal or b.universal or bool(a.layers & b.layers)


def _pt_seg_dist(p, a, b) -> float:
    """Distance from point ``p`` to segment ``a→b`` (all mm tuples)."""
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-18:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _touch(a: Element, b: Element) -> bool:
    if not _layers_touch(a, b):
        return False
    lim = a.radius + b.radius + _EPS_MM
    if len(a.points) == 2 and len(b.points) == 2:
        return (min(_pt_seg_dist(p, b.points[0], b.points[1])
                    for p in a.points) <= lim
                or min(_pt_seg_dist(p, a.points[0], a.points[1])
                       for p in b.points) <= lim)
    if len(a.points) == 2:
        a, b = b, a
    if len(b.points) == 2:
        return _pt_seg_dist(a.points[0], b.points[0], b.points[1]) <= lim
    (ax, ay), (bx, by) = a.points[0], b.points[0]
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 <= lim


@dataclass
class Islands:
    """The copper partition of one net."""

    net: str
    groups: list[list[Element]] = field(default_factory=list)

    def pad_groups(self) -> list[list[Element]]:
        out = []
        for g in self.groups:
            pads = [e for e in g if e.kind == "pad"]
            if pads:
                out.append(pads)
        return out


def net_islands(pcb, net: str) -> Islands:
    """Union-find copper partition of ``net`` (zones merge by bbox)."""
    els = net_elements(pcb, net)
    n = len(els)
    parent = list(range(n + 64))          # + room for zone pseudo-nodes

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    for i in range(n):
        for j in range(i + 1, n):
            if _touch(els[i], els[j]):
                union(i, j)

    # a zone on this net merges every element inside its bbox on its layers
    s = unit_scale(pcb)
    zid = n
    for z in getattr(pcb, "zones", []) or []:
        if z.get("net") != net or not z.get("bbox"):
            continue
        (x0, y0), (x1, y1) = z["bbox"]
        x0, y0, x1, y1 = x0 * s, y0 * s, x1 * s, y1 * s
        zcu, zstar = _copper_layers(z.get("layers"))
        zel = Element(kind="zone", index=-1, points=[], radius=0.0,
                      layers=zcu, universal=zstar or not zcu)
        for i, e in enumerate(els):
            if not _layers_touch(zel, e):
                continue
            if any(x0 - _EPS_MM <= x <= x1 + _EPS_MM
                   and y0 - _EPS_MM <= y <= y1 + _EPS_MM
                   for x, y in e.points):
                union(i, zid)
        zid += 1
        if zid >= len(parent):
            parent.extend(range(len(parent), len(parent) + 64))

    groups: dict[int, list[Element]] = {}
    for i, e in enumerate(els):
        groups.setdefault(find(i), []).append(e)
    return Islands(net=net, groups=list(groups.values()))


# --------------------------------------------------------------------------- #
# distances / lookups
# --------------------------------------------------------------------------- #
def pad_xy_mm(pcb, pad: dict) -> tuple[float, float]:
    s = unit_scale(pcb)
    x, y = pad.get("at") or (0.0, 0.0)
    return x * s, y * s


def pad_distance_mm(pcb, a: dict, b: dict) -> float:
    ax, ay = pad_xy_mm(pcb, a)
    bx, by = pad_xy_mm(pcb, b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def pad_area_mm2(pcb, pad: dict) -> float:
    s = unit_scale(pcb)
    sx, sy = pad.get("size") or (0.0, 0.0)
    return float(sx or 0) * float(sy or 0) * s * s


def vias_in_pad(pcb, pad: dict, margin_mm: float = 0.3) -> list[dict]:
    """Vias on the pad's net whose centre lies inside the pad rect (+margin).

    The pad size is unrotated; a 90°-family rotation swaps the rect. Arbitrary
    angles fall back to the bounding square — over-counting is impossible for
    the usual 0/90 thermal pads and benign otherwise.
    """
    s = unit_scale(pcb)
    px, py = pad_xy_mm(pcb, pad)
    sx, sy = pad.get("size") or (0.0, 0.0)
    sx, sy = float(sx or 0) * s, float(sy or 0) * s
    rot = float(pad.get("rotation") or 0.0) % 180.0
    if abs(rot - 90.0) < 1.0:
        sx, sy = sy, sx
    elif rot > 1.0:
        sx = sy = max(sx, sy)
    hx, hy = sx / 2.0 + margin_mm, sy / 2.0 + margin_mm
    out = []
    for v in getattr(pcb, "vias", []) or []:
        if v.get("net") != pad.get("net"):
            continue
        vx, vy = v.get("at") or (0, 0)
        vx, vy = vx * s, vy * s
        if abs(vx - px) <= hx and abs(vy - py) <= hy:
            out.append(v)
    return out


def min_track_width_mm(pcb, net: str) -> float | None:
    s = unit_scale(pcb)
    widths = [float(t.get("width") or 0) * s
              for t in getattr(pcb, "tracks", []) or []
              if t.get("net") == net and t.get("width")]
    return min(widths) if widths else None


def ipc2221_ampacity_a(width_mm: float, *, dtemp_c: float = 10.0,
                       thickness_mm: float = _OZ_MM,
                       internal: bool = False) -> float:
    """IPC-2221 continuous-current capacity of a track cross-section.

    ``I = k · ΔT^0.44 · A^0.725`` with A in mil² (k = 0.048 external /
    0.024 internal) — the inverse of `akcli calc trackwidth`, which is the
    round-trip oracle in tests.
    """
    k = 0.024 if internal else 0.048
    area_mil2 = (width_mm / 0.0254) * (thickness_mm / 0.0254)
    return k * (dtemp_c ** 0.44) * (area_mil2 ** 0.725)
