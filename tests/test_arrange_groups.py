"""``akcli arrange --groups`` — net-preserving functional-block re-layout.

Relocates each named group into its own shelf-packed region (rigid, carried
moves). The load-bearing guarantee, proven by a before/after netlist diff: with
label-on-pin connectivity the re-layout can NEVER change the netlist — and the
draw pipeline refuses to write if it somehow did.
"""

from __future__ import annotations

import json
from pathlib import Path

from akcli import arrange, cli, netdiff
from akcli.readers import kicad as kreader
from akcli.writers import kicad as kw

DEVICE = Path(__file__).parent / "fixtures" / "kicad" / "symbols" / "Device.kicad_sym"
POWER = Path(__file__).parent / "fixtures" / "kicad" / "symbols" / "power.kicad_sym"


def _oplist(*ops):
    return {"protocol_version": 1, "target_format": "kicad", "ops": list(ops)}


def _seed_two_blocks(tmp_path: Path) -> Path:
    """Two label-only divider blocks (A: R1-R2, B: R3-R4), initially interleaved."""
    tgt = tmp_path / "board.kicad_sch"
    tgt.write_text('(kicad_sch (version 20231120) (generator "akcli") '
                   '(uuid "33333333-4444-5555-6666-777777777777") (paper "A4"))\n')
    ops = []
    # interleave the two blocks in space so a rigid regroup has real work to do
    coords = {"R1": (2000, 1000), "R3": (2200, 1000),
              "R2": (2000, 1400), "R4": (2200, 1400)}
    for ref, (x, y) in coords.items():
        ops.append({"op": "place_component", "lib_id": "Device:R",
                    "designator": ref, "x_mil": x, "y_mil": y, "value": "1k"})
    ops += [
        {"op": "add_net_label", "name": "VINA", "at": "R1.1"},
        {"op": "add_net_label", "name": "MIDA", "at": "R1.2"},
        {"op": "add_net_label", "name": "MIDA", "at": "R2.1"},
        {"op": "add_net_label", "name": "GND", "at": "R2.2"},
        {"op": "add_net_label", "name": "VINB", "at": "R3.1"},
        {"op": "add_net_label", "name": "MIDB", "at": "R3.2"},
        {"op": "add_net_label", "name": "MIDB", "at": "R4.1"},
        {"op": "add_net_label", "name": "GND", "at": "R4.2"},
    ]
    rs = kw.apply(_oplist(*ops), str(tgt), apply=True, sources=[str(DEVICE)])
    assert all(r.status == "ok" for r in rs), [r.message for r in rs]
    return tgt


def _groups_file(tmp_path: Path) -> Path:
    f = tmp_path / "groups.toml"
    f.write_text('[groups]\nblock_a = ["R1", "R2"]\nblock_b = ["R3", "R4"]\n')
    return f


def _nets(tgt: Path):
    return kreader.read_sch(str(tgt)).nets


def _pos(tgt: Path):
    return {c.designator: (c.x_mil, c.y_mil)
            for c in kreader.read_sch(str(tgt)).components}


def test_plan_groups_separates_and_reports(tmp_path):
    tgt = _seed_two_blocks(tmp_path)
    groups = {"block_a": ["R1", "R2"], "block_b": ["R3", "R4"]}
    result = arrange.plan_groups(tgt, groups)
    assert {g["group"] for g in result["groups"]} == {"block_a", "block_b"}
    assert result["unplaced"] == []
    assert {m.ref for m in result["moves"]} <= {"R1", "R2", "R3", "R4"}


def test_arrange_groups_is_net_preserving_end_to_end(tmp_path, capsys):
    tgt = _seed_two_blocks(tmp_path)
    gf = _groups_file(tmp_path)
    before = _nets(tgt)
    capsys.readouterr()
    assert cli.main(["arrange", str(tgt), "--groups", str(gf), "--apply"]) == 0
    after = _nets(tgt)
    # THE guarantee: identical netlist after the re-layout.
    d = netdiff.diff(before, after)
    assert d.equivalent, netdiff.format_summary(d)

    # blocks are now spatially separated (B sits below A, past the gap)
    pos = _pos(tgt)
    a_bottom = max(pos["R1"][1], pos["R2"][1])
    b_top = min(pos["R3"][1], pos["R4"][1])
    assert b_top > a_bottom

    # went through the draw pipeline -> undo reverts it
    assert cli.main(["undo", str(tgt), "--apply"]) == 0
    capsys.readouterr()
    assert netdiff.diff(before, _nets(tgt)).equivalent


def test_arrange_groups_json_dry_run_writes_nothing(tmp_path, capsys):
    tgt = _seed_two_blocks(tmp_path)
    gf = _groups_file(tmp_path)
    before = _pos(tgt)
    capsys.readouterr()
    assert cli.main(["arrange", str(tgt), "--groups", str(gf), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["applied"] is False and doc["moves"]
    assert _pos(tgt) == before          # dry-run never writes


def test_power_port_rides_with_its_host(tmp_path, capsys):
    """A #PWR GND port on a component pin must relocate with that component."""
    tgt = tmp_path / "board.kicad_sch"
    tgt.write_text('(kicad_sch (version 20231120) (generator "akcli") '
                   '(uuid "44444444-5555-6666-7777-888888888888") (paper "A4"))\n')
    rs = kw.apply(_oplist(
        {"op": "place_component", "lib_id": "Device:R", "designator": "R1",
         "x_mil": 2000, "y_mil": 1000, "value": "1k"},
        {"op": "place_component", "lib_id": "Device:R", "designator": "R2",
         "x_mil": 3000, "y_mil": 1000, "value": "1k"},
        {"op": "add_net_label", "name": "IN", "at": "R1.1"},
        {"op": "place_power_port", "lib_id": "power:GND", "net_name": "GND",
         "at": "R1.2"},
        {"op": "add_net_label", "name": "IN2", "at": "R2.1"},
        {"op": "place_power_port", "lib_id": "power:GND", "net_name": "GND",
         "at": "R2.2"},
    ), str(tgt), apply=True, sources=[str(DEVICE), str(POWER)])
    assert all(r.status == "ok" for r in rs), [r.message for r in rs]
    before = _nets(tgt)
    gf = tmp_path / "g.json"
    gf.write_text('{"block": ["R1"], "block2": ["R2"]}')
    capsys.readouterr()
    assert cli.main(["arrange", str(tgt), "--groups", str(gf), "--apply",
                     "--symbols", str(DEVICE), "--symbols", str(POWER)]) == 0
    # net-preserving means the GND port stayed glued to R1.2 through the move
    assert netdiff.diff(before, _nets(tgt)).equivalent
