"""Self-contained validation of the synthetic KiCad fixtures.

This test deliberately does NOT import any reader module (the KiCad readers are
built by a separate workflow). It carries a tiny self-contained S-expression
parser so it can prove that the hand-authored fixtures are:

  * well-formed S-expressions (balanced, quotes closed),
  * complete (lib_symbols cache, instances, wires, junctions, labels, power),
  * format-version-distinct between KiCad 7 and KiCad 8, and
  * internally consistent: the hand-placed wire endpoints actually coincide with
    the pin world-coordinates computed from the lib_symbols cache, so a real
    reader + netbuild will derive the three intended nets.
"""

from __future__ import annotations

from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "kicad"
V7 = FIX / "board_v7.kicad_sch"
V8 = FIX / "board_v8.kicad_sch"
DEVICE_SYM = FIX / "symbols" / "Device.kicad_sym"
POWER_SYM = FIX / "symbols" / "power.kicad_sym"


# --------------------------------------------------------------------------- #
# Minimal, dependency-free S-expression parser.
# --------------------------------------------------------------------------- #
def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "() ":
            if c in "()":
                toks.append(c)
            i += 1
        elif c in " \t\r\n":
            i += 1
        elif c == '"':
            i += 1
            buf = []
            while i < n:
                ch = text[i]
                if ch == "\\":
                    buf.append(text[i : i + 2])
                    i += 2
                    continue
                if ch == '"':
                    i += 1
                    break
                buf.append(ch)
                i += 1
            else:
                raise ValueError("unterminated string")
            toks.append('"' + "".join(buf))  # marker prefix => quoted atom
        else:
            buf = []
            while i < n and text[i] not in "() \t\r\n":
                buf.append(text[i])
                i += 1
            toks.append("".join(buf))
    return toks


def parse(text: str):
    toks = tokenize(text)
    pos = 0

    def build():
        nonlocal pos
        assert toks[pos] == "(", "expected ("
        pos += 1
        node: list = []
        while pos < len(toks):
            t = toks[pos]
            if t == "(":
                node.append(build())
            elif t == ")":
                pos += 1
                return node
            else:
                pos += 1
                node.append(t[1:] if t.startswith('"') else t)
        raise ValueError("unbalanced parens")

    node = build()
    assert pos == len(toks), "trailing tokens after top-level node"
    return node


def is_list(x) -> bool:
    return isinstance(x, list)


def head(node) -> str | None:
    return node[0] if is_list(node) and node and isinstance(node[0], str) else None


def children(node, name: str):
    return [c for c in node if is_list(c) and head(c) == name]


def find_all(node, name: str):
    out = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if is_list(cur):
            if head(cur) == name:
                out.append(cur)
            for c in cur:
                if is_list(c):
                    stack.append(c)
    return out


def i100(s: str) -> int:
    return round(float(s) * 100)


# --------------------------------------------------------------------------- #
# Structural checks
# --------------------------------------------------------------------------- #
def test_all_fixtures_are_balanced_sexpr():
    for p in (V7, V8, DEVICE_SYM, POWER_SYM):
        node = parse(p.read_text())
        assert head(node) in ("kicad_sch", "kicad_symbol_lib"), p.name


def test_device_lib_has_r_c_l_and_polarized_extends():
    lib = parse(DEVICE_SYM.read_text())
    names = {s[1] for s in children(lib, "symbol")}
    assert {"R", "C", "L", "C_Polarized"} <= names
    cpol = next(s for s in children(lib, "symbol") if s[1] == "C_Polarized")
    ext = children(cpol, "extends")
    assert ext and ext[0][1] == "C"
    # C_Polarized inherits pins from C: it defines none of its own.
    assert not find_all(cpol, "pin")
    # R/C/L each expose two numbered pins carrying an electrical type.
    for name in ("R", "C", "L"):
        sym = next(s for s in children(lib, "symbol") if s[1] == name)
        pins = find_all(sym, "pin")
        assert len(pins) == 2, name
        for pin in pins:
            assert pin[1] in {
                "input", "output", "bidirectional", "tri_state", "passive",
                "power_in", "power_out", "open_collector", "open_emitter",
                "free", "unspecified", "no_connect",
            }, pin[1]


def test_power_lib_has_gnd_and_3v3():
    lib = parse(POWER_SYM.read_text())
    names = {s[1] for s in children(lib, "symbol")}
    assert {"GND", "+3V3"} <= names
    for name in ("GND", "+3V3"):
        sym = next(s for s in children(lib, "symbol") if s[1] == name)
        assert children(sym, "power"), name
        assert len(find_all(sym, "pin")) == 1


def test_version_markers_differ_between_v7_and_v8():
    t7, t8 = V7.read_text(), V8.read_text()
    assert "(version 20230121)" in t7
    assert "(version 20231120)" in t8
    # v8-only format markers
    assert "(generator_version" in t8 and "(generator_version" not in t7
    assert "(hide yes)" in t8 and "(hide yes)" not in t7
    assert "exclude_from_sim" in t8 and "exclude_from_sim" not in t7
    assert "(fields_autoplaced yes)" in t8
    # v7 uses bare hide tokens
    assert "(fields_autoplaced)" in t7
    assert "(pin_numbers hide)" in t7


def _completeness(node):
    assert children(node, "lib_symbols"), "missing lib_symbols cache"
    assert len(find_all(node, "wire")) == 5
    assert len(find_all(node, "junction")) == 2
    assert len(children(node, "label")) == 1
    assert len(children(node, "global_label")) == 1
    placed = [
        s for s in children(node, "symbol") if children(s, "lib_id")
    ]
    assert len(placed) == 5
    refs = set()
    for s in placed:
        assert children(s, "instances"), "instance block missing"
        prop = next(c for c in children(s, "property") if c[1] == "Reference")
        refs.add(prop[2])
    assert {"R1", "R2", "C1", "#PWR01", "#PWR02"} == refs
    lib_ids = {children(s, "lib_id")[0][1] for s in placed}
    assert {"power:+3V3", "power:GND"} <= lib_ids


def test_v7_complete():
    _completeness(parse(V7.read_text()))


def test_v8_complete():
    _completeness(parse(V8.read_text()))


# --------------------------------------------------------------------------- #
# Net derivation: prove wires hit pins and the three nets form correctly.
# --------------------------------------------------------------------------- #
def _pin_offsets(node) -> dict[str, list[tuple[str, int, int]]]:
    """lib_id -> [(pin_number, lx100, ly100)] from the inline lib_symbols cache."""
    libsym = children(node, "lib_symbols")[0]
    out: dict[str, list[tuple[str, int, int]]] = {}
    for sym in children(libsym, "symbol"):
        lib_id = sym[1]
        pins = []
        for pin in find_all(sym, "pin"):
            at = children(pin, "at")[0]
            num = children(pin, "number")[0][1]
            pins.append((num, i100(at[1]), i100(at[2])))
        out[lib_id] = pins
    return out


def _on_seg(p, a, b) -> bool:
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if cross != 0:
        return False
    return (
        min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
    )


class _UF:
    def __init__(self):
        self.p: dict = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _derive_nets(path: Path):
    node = parse(path.read_text())
    offs = _pin_offsets(node)

    pin_world: dict[tuple[str, str], tuple[int, int]] = {}
    for s in children(node, "symbol"):
        libid_node = children(s, "lib_id")
        if not libid_node:
            continue
        lib_id = libid_node[0][1]
        at = children(s, "at")[0]
        px, py, rot = i100(at[1]), i100(at[2]), int(float(at[3]))
        assert rot == 0, "fixtures use rotation 0 only"
        ref = next(c for c in children(s, "property") if c[1] == "Reference")[2]
        for num, lx, ly in offs[lib_id]:
            pin_world[(ref, num)] = (px + lx, py - ly)  # KiCad +Y-up library flip

    segs = []
    for w in find_all(node, "wire"):
        pts = children(w, "pts")[0]
        xys = children(pts, "xy")
        a = (i100(xys[0][1]), i100(xys[0][2]))
        b = (i100(xys[1][1]), i100(xys[1][2]))
        segs.append((a, b))

    points = set()
    for a, b in segs:
        points.add(a)
        points.add(b)
    for j in find_all(node, "junction"):
        at = children(j, "at")[0]
        points.add((i100(at[1]), i100(at[2])))
    points.update(pin_world.values())

    uf = _UF()
    for a, b in segs:
        uf.union(a, b)
        for p in points:
            if _on_seg(p, a, b):
                uf.union(p, a)

    nets: dict = {}
    for ref_pin, pt in pin_world.items():
        nets.setdefault(uf.find(pt), set()).add(ref_pin)
    return nets, pin_world, uf


def _net_of(nets, pin_world, uf, ref_pin):
    return nets[uf.find(pin_world[ref_pin])]


def _check_topology(path: Path):
    nets, pin_world, uf = _derive_nets(path)

    mid = _net_of(nets, pin_world, uf, ("R1", "2"))
    gnd = _net_of(nets, pin_world, uf, ("R2", "2"))
    v33 = _net_of(nets, pin_world, uf, ("R1", "1"))

    # MID: R1.2, R2.1, C1.1  (resistor divider midpoint + cap top)
    assert {("R1", "2"), ("R2", "1"), ("C1", "1")} <= mid
    assert ("R1", "1") not in mid and ("R2", "2") not in mid

    # GND: R2.2, C1.2, plus the GND power pin (T-junction merge of two wires)
    assert {("R2", "2"), ("C1", "2"), ("#PWR02", "1")} <= gnd

    # +3V3: R1.1 plus the +3V3 power pin; no divider pins leak in
    assert {("R1", "1"), ("#PWR01", "1")} <= v33
    assert ("R1", "2") not in v33

    # The three nets are genuinely distinct.
    assert uf.find(pin_world[("R1", "2")]) != uf.find(pin_world[("R2", "2")])
    assert uf.find(pin_world[("R1", "1")]) != uf.find(pin_world[("R1", "2")])


def test_v7_net_topology():
    _check_topology(V7)


def test_v8_net_topology():
    _check_topology(V8)


def test_v7_v8_same_circuit():
    n7, pw7, uf7 = _derive_nets(V7)
    n8, pw8, uf8 = _derive_nets(V8)
    assert pw7 == pw8  # identical pin world-coordinates
    groups7 = {frozenset(s) for s in n7.values()}
    groups8 = {frozenset(s) for s in n8.values()}
    assert groups7 == groups8
