"""PCB-family review detectors + copper geometry (M5).

Geometry fixtures are hand-built :class:`~akcli.model.Pcb` objects (mm
frame); the end-to-end positive rides the real ``board.kicad_pcb`` fixture,
which is genuinely unrouted (pads, no tracks) — both its nets must split
into islands.
"""

from __future__ import annotations

import json
from pathlib import Path

from akcli import cli
from akcli.model import Footprint, Pcb
from akcli.review import engine, facts as fx, geometry, topo
from akcli.review.detectors.pcb import decap, routing, thermal, trace_width

FIXTURE_PCB = Path(__file__).parent / "fixtures" / "kicad" / "board.kicad_pcb"
FIXTURE_SCH = Path(__file__).parent / "fixtures" / "kicad" / "board_v8.kicad_sch"


def _pad(ref, num, net, x, y, size=(1.0, 1.0), layers=("F.Cu",),
         pad_type="smd", rotation=0.0):
    return {"component": ref, "number": num, "pad_type": pad_type,
            "shape": "rect", "at": (x, y), "size": size,
            "rotation": rotation, "layers": list(layers),
            "footprint_layer": "F.Cu", "drill": None, "net": net}


def _track(net, x1, y1, x2, y2, width=0.25, layer="F.Cu"):
    return {"start": (x1, y1), "end": (x2, y2), "width": width,
            "layer": layer, "net": net}


def _via(net, x, y, size=0.6, layers=("F.Cu", "B.Cu"), kind="through"):
    return {"at": (x, y), "size": size, "drill": 0.3,
            "layers": list(layers), "type": kind, "net": net}


def _pcb(nets, pads=(), tracks=(), vias=(), zones=(), footprints=()):
    return Pcb(source_path="<test>", source_format="kicad", nets=list(nets),
               footprints=list(footprints), pads=list(pads),
               tracks=list(tracks), vias=list(vias), zones=list(zones),
               board={"units": "mm"})


def _ctx(pcb, facts=None):
    from akcli.model import Schematic
    sch = Schematic(source_path="<none>", source_format="kicad",
                    components=[], nets=[])
    return topo.build_ctx(sch, pcb, facts)


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
def test_islands_split_and_joined_by_track():
    pads = [_pad("R1", "1", "N", 0, 0), _pad("C1", "1", "N", 10, 0)]
    split = geometry.net_islands(_pcb(["N"], pads), "N")
    assert len(split.pad_groups()) == 2
    joined = geometry.net_islands(
        _pcb(["N"], pads, [_track("N", 0, 0, 10, 0)]), "N")
    assert len(joined.pad_groups()) == 1


def test_islands_respect_layers_and_vias_bridge():
    pads = [_pad("R1", "1", "N", 0, 0, layers=("F.Cu",)),
            _pad("C1", "1", "N", 10, 0, layers=("B.Cu",))]
    fcu_track = [_track("N", 0, 0, 10, 0, layer="F.Cu")]
    # F.Cu track cannot reach a B.Cu-only pad …
    assert len(geometry.net_islands(
        _pcb(["N"], pads, fcu_track), "N").pad_groups()) == 2
    # … until a through via bridges the layers at the far end
    assert len(geometry.net_islands(
        _pcb(["N"], pads, fcu_track, [_via("N", 10, 0)]), "N")
        .pad_groups()) == 1


def test_islands_t_junction_and_zone_merge():
    pads = [_pad("R1", "1", "N", 0, 0), _pad("C1", "1", "N", 5, 5)]
    tee = [_track("N", 0, 0, 10, 0), _track("N", 5, 0, 5, 5)]
    assert len(geometry.net_islands(_pcb(["N"], pads, tee), "N")
               .pad_groups()) == 1
    # zone bbox merge: no copper at all, one zone covering both pads
    zone = [{"net": "N", "layers": ["F.Cu"], "name": None,
             "bbox": ((-1, -1), (11, 11))}]
    assert len(geometry.net_islands(_pcb(["N"], pads, zones=zone), "N")
               .pad_groups()) == 1


def test_unit_scale_mil_boards():
    p = _pcb(["N"])
    p.board = {"units": "mil"}
    assert geometry.unit_scale(p) == 0.0254
    assert geometry.unit_scale(_pcb(["N"])) == 1.0


def test_ipc2221_roundtrips_against_calc_trackwidth():
    from akcli.calc import compute
    width_mm = 0.5
    amps = geometry.ipc2221_ampacity_a(width_mm, dtemp_c=10.0)
    env = compute("trackwidth", {"i": amps, "dtemp": 10.0})
    back_mm = env["results"]["external_width"]["value"] * 1000.0
    assert abs(back_mm - width_mm) / width_mm < 0.01


# --------------------------------------------------------------------------- #
# detectors
# --------------------------------------------------------------------------- #
def test_routing_unrouted_positive_and_routed_negative():
    pads = [_pad("R1", "1", "N", 0, 0), _pad("C1", "1", "N", 10, 0)]
    fs = routing.run(_ctx(_pcb(["N"], pads)))
    assert [f.code for f in fs] == ["REVIEW_PCB_UNROUTED"]
    assert fs[0].confidence == "deterministic"
    assert routing.run(_ctx(_pcb(["N"], pads,
                                 [_track("N", 0, 0, 10, 0)]))) == []


def test_decap_far_and_near():
    pads = [_pad("U1", "8", "+3V3", 0, 0),
            _pad("C1", "1", "+3V3", 8, 0),          # 8 mm away → far
            _pad("C2", "1", "+3V3", 1.5, 0)]        # 1.5 mm → fine
    fs = decap.run(_ctx(_pcb(["+3V3"], pads)))
    assert [f.code for f in fs] == ["REVIEW_DECAP_DISTANCE"]
    assert "C1" in fs[0].refs
    assert abs(fs[0].evidence["calc"]["distance_mm"] - 8.0) < 0.01
    assert fs[0].fix_params["kind"] == "move_decap"


def test_decap_without_ic_on_net_is_silent():
    pads = [_pad("C1", "1", "+3V3", 8, 0), _pad("R1", "1", "+3V3", 0, 0)]
    assert decap.run(_ctx(_pcb(["+3V3"], pads))) == []


def test_thermal_via_floor():
    ep = _pad("U1", "EP", "GND", 0, 0, size=(3.0, 3.0))   # 9 mm² thermal pad
    few = [_via("GND", 0.5, 0.5), _via("GND", -0.5, -0.5)]
    fs = thermal.run(_ctx(_pcb(["GND"], [ep], vias=few)))
    assert [f.code for f in fs] == ["REVIEW_THERMAL_VIA"]
    assert fs[0].evidence["calc"]["vias"] == 2
    enough = few + [_via("GND", 0.5, -0.5), _via("GND", -0.5, 0.5)]
    assert thermal.run(_ctx(_pcb(["GND"], [ep], vias=enough))) == []
    # small pad: not a thermal pad
    small = _pad("U1", "1", "GND", 0, 0, size=(1.0, 1.0))
    assert thermal.run(_ctx(_pcb(["GND"], [small]))) == []


def _theta_store(mpn, theta=None, p=None, tj_max=None):
    f = fx.Facts(mpn=mpn, sha256="cd" * 32, pdf="x.pdf")
    for key, val, unit in (("theta_ja", theta, "K/W"),
                           ("power_dissipation", p, "W"),
                           ("t_j_max", tj_max, "°C")):
        if val is not None:
            f.values[key] = fx.FactValue(key=key, unit=unit, page=9,
                                         value=val, sha256=f.sha256)
    store = fx.FactsStore()
    store.by_mpn[mpn.upper()] = f
    return store


def test_junction_datasheet_backed_over_limit():
    fps = [Footprint(designator="U1", footprint_name="Package_TO_SOT_SMD:SOT-23",
                     layer="F.Cu", value="LDO123X")]
    store = _theta_store("LDO123X", theta=250.0, p=0.5)   # 25 + 125 = 150 °C
    fs = thermal.run(_ctx(_pcb([], footprints=fps), facts=store))
    assert [f.code for f in fs] == ["REVIEW_THERMAL_JUNCTION"]
    f = fs[0]
    assert f.severity.value == "warning" and f.confidence == "datasheet_backed"
    assert f.evidence["calc"]["results"]["tj_c"] == 150.0
    assert f.evidence["datasheet"]["page"] == 9


def test_junction_package_table_fallback_is_heuristic():
    fps = [Footprint(designator="U1", footprint_name="SOT-223-3_TabPin2",
                     layer="F.Cu", value="REG78X")]
    store = _theta_store("REG78X", p=0.5)          # θ from table: 60 K/W
    fs = thermal.run(_ctx(_pcb([], footprints=fps), facts=store))
    assert [f.code for f in fs] == ["REVIEW_THERMAL_JUNCTION"]
    f = fs[0]
    assert f.severity.value == "info" and f.confidence == "heuristic"
    assert f.evidence["calc"]["results"]["tj_c"] == 55.0   # 25 + 0.5·60


def test_junction_without_dissipation_is_silent():
    fps = [Footprint(designator="U1", footprint_name="SOT-23", layer="F.Cu",
                     value="LDO123X")]
    store = _theta_store("LDO123X", theta=250.0)   # no power_dissipation
    assert thermal.run(_ctx(_pcb([], footprints=fps), facts=store)) == []


def test_trace_width_reports_ampacity_on_power_nets():
    tracks = [_track("+3V3", 0, 0, 10, 0, width=0.3),
              _track("+3V3", 10, 0, 20, 0, width=0.6),
              _track("SIG", 0, 5, 10, 5, width=0.15)]
    fs = trace_width.run(_ctx(_pcb(["+3V3", "SIG"], tracks=tracks)))
    assert [f.code for f in fs] == ["REVIEW_TRACE_WIDTH"]     # SIG not a rail
    f = fs[0]
    assert "0.3" in f.message                                  # thinnest wins
    amps = geometry.ipc2221_ampacity_a(0.3)
    assert f"{amps:.2g}" in f.message
    assert f.evidence["calc"]["calc"] == "trackwidth"          # oracle envelope


# --------------------------------------------------------------------------- #
# engine + CLI end-to-end
# --------------------------------------------------------------------------- #
def test_engine_skips_pcb_family_without_board():
    from akcli.model import Schematic
    sch = Schematic(source_path="<t>", source_format="kicad",
                    components=[], nets=[])
    _fs, meta = engine.analyze(sch, profile="standard")
    assert "pcb.routing" in meta["detectors_skipped"]
    assert "pcb.routing" not in meta["detectors_run"]


def test_cli_analyze_with_pcb_finds_unrouted_fixture(tmp_path, capsys):
    assert cli.main(["review", "analyze", str(FIXTURE_SCH),
                     "--pcb", str(FIXTURE_PCB), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    unrouted = [f for f in doc["findings"]
                if f["code"] == "REVIEW_PCB_UNROUTED"]
    assert {f["refs"][0] for f in unrouted} == {"+3V3", "GND"}
    assert "pcb.routing" in doc["metadata"]["detectors_run"]
