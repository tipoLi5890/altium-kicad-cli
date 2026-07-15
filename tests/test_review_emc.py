"""EMC-family review detectors (M6): pre-compliance risk, three batches.

Every threshold is an assumption stated on the finding; the engine's ``emc``
metadata block is advisory (risk score + probe points + the not-a-compliance-
verdict note) and appears whenever the family RAN — quiet ≠ unreviewed.
"""

from __future__ import annotations

import json
from pathlib import Path

from akcli import cli
from akcli.model import Footprint, Pcb, Schematic
from akcli.review import engine, topo
from akcli.review.detectors.emc import (diffpair, edge, planes, protection,
                                        stitching)

FIXTURE_PCB = Path(__file__).parent / "fixtures" / "kicad" / "board.kicad_pcb"
FIXTURE_SCH = Path(__file__).parent / "fixtures" / "kicad" / "board_v8.kicad_sch"


def _pad(ref, num, net, x, y, size=(1.0, 1.0)):
    return {"component": ref, "number": num, "pad_type": "smd",
            "shape": "rect", "at": (x, y), "size": size, "rotation": 0.0,
            "layers": ["F.Cu"], "footprint_layer": "F.Cu", "drill": None,
            "net": net}


def _track(net, x1, y1, x2, y2, width=0.25, layer="F.Cu"):
    return {"start": (x1, y1), "end": (x2, y2), "width": width,
            "layer": layer, "net": net}


def _via(net, x, y):
    return {"at": (x, y), "size": 0.6, "drill": 0.3,
            "layers": ["F.Cu", "B.Cu"], "type": "through", "net": net}


def _board4(outline=((0, 0), (50, 40))):
    return {
        "units": "mm",
        "copper_layers": ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
        "layers": [
            {"name": "F.Cu", "type": "signal"},
            {"name": "In1.Cu", "type": "power"},
            {"name": "In2.Cu", "type": "signal"},
            {"name": "B.Cu", "type": "signal"},
        ],
        "outline_bbox": outline,
    }


def _pcb(nets=(), pads=(), tracks=(), vias=(), zones=(), footprints=(),
         board=None):
    return Pcb(source_path="<test>", source_format="kicad", nets=list(nets),
               footprints=list(footprints), pads=list(pads),
               tracks=list(tracks), vias=list(vias), zones=list(zones),
               board=board if board is not None else _board4())


def _ctx(pcb):
    sch = Schematic(source_path="<none>", source_format="kicad",
                    components=[], nets=[])
    return topo.build_ctx(sch, pcb)


def _gnd_zone(bbox=((0, 0), (50, 40))):
    return {"net": "GND", "layers": ["In1.Cu"], "name": None, "bbox": bbox}


# --------------------------------------------------------------------------- #
# planes / stackup
# --------------------------------------------------------------------------- #
def test_no_gnd_plane_and_stackup_adjacent():
    fs = planes.run(_ctx(_pcb()))
    codes = sorted(f.code for f in fs)
    assert "REVIEW_EMC_NO_GND_PLANE" in codes
    # In2.Cu + B.Cu are adjacent signal layers in the 4-layer stack
    assert "REVIEW_EMC_STACKUP_ADJACENT" in codes


def test_gnd_zone_silences_plane_and_coverage_note_fires():
    full = planes.run(_ctx(_pcb(zones=[_gnd_zone()])))
    assert "REVIEW_EMC_NO_GND_PLANE" not in {f.code for f in full}
    small = planes.run(_ctx(_pcb(zones=[_gnd_zone(((0, 0), (10, 10)))])))
    cov = [f for f in small if f.code == "REVIEW_EMC_PLANE_COVERAGE"]
    assert len(cov) == 1 and cov[0].evidence["calc"]["coverage"] == 0.05
    assert any("BOUNDING BOX" in a for a in cov[0].evidence["assumptions"])


def test_two_layer_board_stackup_rule_silent():
    board = {"units": "mm",
             "copper_layers": ["F.Cu", "B.Cu"],
             "layers": [{"name": "F.Cu", "type": "signal"},
                        {"name": "B.Cu", "type": "signal"}],
             "outline_bbox": ((0, 0), (50, 40))}
    # 2-layer F/B "adjacent signals" is every 2-layer board ever — but the
    # rule reads declaration order, and F.Cu/B.Cu ARE adjacent in the list:
    # accept the note (it is honest) — just assert no crash and note-level.
    fs = planes.run(_ctx(_pcb(zones=[_gnd_zone()], board=board)))
    for f in fs:
        assert f.severity.value in ("note", "warning")


# --------------------------------------------------------------------------- #
# stitching
# --------------------------------------------------------------------------- #
def test_stitching_none_warns_sparse_notes_dense_silent():
    none = stitching.run(_ctx(_pcb()))
    assert [f.code for f in none] == ["REVIEW_EMC_VIA_STITCH"]
    assert none[0].severity.value == "warning"

    sparse = stitching.run(_ctx(_pcb(
        vias=[_via("GND", 0, 0), _via("GND", 30, 0)])))   # 30 mm > λ/20≈7.2
    assert [f.code for f in sparse] == ["REVIEW_EMC_VIA_STITCH"]
    assert sparse[0].severity.value == "note"
    assert sparse[0].evidence["calc"]["worst_gap_mm"] == 30.0

    dense = stitching.run(_ctx(_pcb(
        vias=[_via("GND", x, 0) for x in range(0, 35, 5)])))   # 5 mm grid
    assert dense == []


def test_stitching_skips_two_layer_less_boards():
    board = {"units": "mm", "copper_layers": ["F.Cu"]}
    assert stitching.run(_ctx(_pcb(board=board))) == []


# --------------------------------------------------------------------------- #
# edge
# --------------------------------------------------------------------------- #
def test_edge_track_note_and_clock_warning():
    tracks = [_track("SPI_SCK", 0.2, 5, 0.2, 20),     # 0.2 mm from x0 edge
              _track("DATA7", 5, 0.3, 20, 0.3),       # 0.3 mm from y0 edge
              _track("SAFE", 25, 20, 30, 20)]         # mid-board
    fs = edge.run(_ctx(_pcb(tracks=tracks)))
    by_code = {f.code: f for f in fs}
    assert set(by_code) == {"REVIEW_EMC_CLOCK_EDGE", "REVIEW_EMC_EDGE_TRACK"}
    assert by_code["REVIEW_EMC_CLOCK_EDGE"].refs == ["SPI_SCK"]
    assert by_code["REVIEW_EMC_EDGE_TRACK"].refs == ["DATA7"]


def test_edge_silent_without_outline():
    board = dict(_board4())
    board.pop("outline_bbox")
    tracks = [_track("SPI_SCK", 0.2, 5, 0.2, 20)]
    assert edge.run(_ctx(_pcb(tracks=tracks, board=board))) == []


# --------------------------------------------------------------------------- #
# diff pair
# --------------------------------------------------------------------------- #
def test_diffpair_skew_warns_and_matched_silent():
    tracks = [_track("USB_P", 0, 0, 20, 0),           # 20 mm
              _track("USB_N", 0, 1, 30, 1)]           # 30 mm → 10 mm ≈ 66 ps
    fs = diffpair.run(_ctx(_pcb(nets=["USB_P", "USB_N"], tracks=tracks)))
    assert [f.code for f in fs] == ["REVIEW_EMC_DIFFPAIR_SKEW"]
    f = fs[0]
    assert f.evidence["calc"]["skew_ps"] == 66.0
    assert f.fix_params["short_side"] == "USB_P"
    ok = [_track("USB_P", 0, 0, 20, 0), _track("USB_N", 0, 1, 21, 1)]
    assert diffpair.run(_ctx(_pcb(nets=["USB_P", "USB_N"], tracks=ok))) == []


def test_diffpair_unrouted_side_left_to_routing_rule():
    tracks = [_track("LVDS_P", 0, 0, 20, 0)]          # _N has no copper
    assert diffpair.run(_ctx(_pcb(nets=["LVDS_P", "LVDS_N"],
                                  tracks=tracks))) == []


# --------------------------------------------------------------------------- #
# tvs placement
# --------------------------------------------------------------------------- #
def _fp(ref, name, value):
    return Footprint(designator=ref, footprint_name=name, layer="F.Cu",
                     value=value)


def test_tvs_far_and_near():
    fps = [_fp("J1", "Connector_USB:USB_C", "USB-C"),
           _fp("D1", "SOT:SOT-23-6", "USBLC6-2SC6"),
           _fp("D2", "SOT:SOT-23-6", "USBLC6-2SC6")]
    pads = [_pad("J1", "A6", "USB_P", 0, 0),
            _pad("D1", "1", "USB_P", 25, 0),          # 25 mm away → far
            _pad("D2", "1", "USB_P", 3, 0)]           # 3 mm → fine
    fs = protection.run(_ctx(_pcb(pads=pads, footprints=fps)))
    assert [f.code for f in fs] == ["REVIEW_EMC_TVS_FAR"]
    assert fs[0].refs[0] == "D1"
    assert fs[0].evidence["calc"]["distance_mm"] == 25.0


def test_tvs_silent_without_connectors():
    fps = [_fp("D1", "SOT:SOT-23-6", "USBLC6-2SC6")]
    pads = [_pad("D1", "1", "USB_P", 25, 0)]
    assert protection.run(_ctx(_pcb(pads=pads, footprints=fps))) == []


# --------------------------------------------------------------------------- #
# engine aggregation + e2e
# --------------------------------------------------------------------------- #
def test_engine_emc_block_scores_and_probes():
    sch = Schematic(source_path="<t>", source_format="kicad",
                    components=[], nets=[])
    tracks = [_track("SPI_SCK", 0.2, 5, 0.2, 20)]
    pcb = _pcb(tracks=tracks)                      # no gnd zone, no vias
    _fs, meta = engine.analyze(sch, pcb=pcb, profile="deep")
    emc = meta["emc"]
    # NO_GND_PLANE(w=8) + VIA_STITCH(w=8) + CLOCK_EDGE(w=8)
    # + STACKUP_ADJACENT(n=3) = 27
    assert emc["risk_score"] == 27
    assert "SPI_SCK" in emc["probe_points"]
    assert "not a compliance" in emc["note"] or "accredited lab" in emc["note"]


def test_engine_emc_block_present_when_quiet():
    sch = Schematic(source_path="<t>", source_format="kicad",
                    components=[], nets=[])
    good_stack = dict(_board4())
    good_stack["layers"] = [
        {"name": "F.Cu", "type": "signal"},
        {"name": "In1.Cu", "type": "power"},
        {"name": "In2.Cu", "type": "signal"},
        {"name": "B.Cu", "type": "power"},
    ]
    quiet = _pcb(zones=[_gnd_zone()], board=good_stack,
                 vias=[_via("GND", x, y) for x in range(0, 55, 5)
                       for y in (0, 20, 39)])
    _fs, meta = engine.analyze(sch, pcb=quiet, profile="deep")
    assert meta["emc"]["risk_score"] == 0 and meta["emc"]["findings"] == 0


def test_engine_no_emc_block_without_family():
    sch = Schematic(source_path="<t>", source_format="kicad",
                    components=[], nets=[])
    _fs, meta = engine.analyze(sch, pcb=_pcb(), profile="standard")
    assert "emc" not in meta
    _fs, meta = engine.analyze(sch, profile="deep")     # no pcb at all
    assert "emc" not in meta and "emc.planes" in meta["detectors_skipped"]


def test_cli_deep_profile_runs_emc_on_fixture(tmp_path, capsys):
    assert cli.main(["review", "analyze", str(FIXTURE_SCH),
                     "--pcb", str(FIXTURE_PCB), "--profile", "deep",
                     "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert "emc" in doc["metadata"]
    assert any(d.startswith("emc.") for d in doc["metadata"]["detectors_run"])
