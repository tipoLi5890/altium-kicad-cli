"""Tests for the Altium ``.PcbDoc`` -> ``model.Pcb`` reader (ASCII sections only).

Parses Nets6 / Components6 / Classes6 / Rules6; refuses to ASCII-parse a binary
geometry section (Pads6 / Tracks6 / ...) loudly. Fixtures are built at test time
from the committed pure-stdlib generators.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from altium_kicad_cli.errors import AkcliError
from altium_kicad_cli.readers import _cfbf, altium_pcb

GEN = Path(__file__).resolve().parent / "fixtures" / "_gen"
if str(GEN) not in sys.path:
    sys.path.insert(0, str(GEN))
import altium_fixture  # noqa: E402
import ole_writer  # noqa: E402


def _frame_records(records: list[dict]) -> bytes:
    return b"".join(bytes(altium_fixture._frame(r)) for r in records)


def _write_pcb(tmp_path: Path) -> Path:
    streams = {
        "FileHeader": _frame_records([{"HEADER": "PCB 6.0 Binary File"}]),
        "Nets6/Data": _frame_records([
            {"NAME": "GND"}, {"NAME": "V3V3"}, {"NAME": "SIG0"},
        ]),
        "Components6/Data": _frame_records([
            {"SOURCEDESIGNATOR": "U1", "PATTERN": "QFN48", "LAYER": "TOP",
             "ROTATION": "90", "COMMENT": "nRF52833"},
            {"SOURCEDESIGNATOR": "R1", "PATTERN": "0402", "LAYER": "TOP",
             "ROTATION": "0"},
        ]),
        "Classes6/Data": _frame_records([
            {"NAME": "PowerNets", "SUPERCLASS": "FALSE"},
        ]),
        "Rules6/Data": _frame_records([
            {"NAME": "Clearance", "RULEKIND": "Clearance"},
        ]),
        # a binary section present in the container -- never ASCII-parsed.
        "Pads6/Data": bytes(range(64)),
    }
    p = tmp_path / "board.PcbDoc"
    ole_writer.write_ole(str(p), streams)
    return p


def test_nets_parsed(tmp_path):
    pcb = altium_pcb.read(_write_pcb(tmp_path))
    assert pcb.nets == ["GND", "V3V3", "SIG0"]
    assert pcb.source_format == "altium"


def test_components_parsed_as_footprints(tmp_path):
    pcb = altium_pcb.read(_write_pcb(tmp_path))
    by_des = {f.designator: f for f in pcb.footprints}
    assert set(by_des) == {"U1", "R1"}
    assert by_des["U1"].footprint_name == "QFN48"
    assert by_des["U1"].layer == "TOP"
    assert by_des["U1"].rotation == 90.0
    assert by_des["U1"].value == "nRF52833"
    assert by_des["R1"].rotation == 0.0


def test_classes_and_rules_parsed(tmp_path):
    pcb = altium_pcb.read(_write_pcb(tmp_path))
    assert pcb.classes and pcb.classes[0]["NAME"] == "PowerNets"
    assert pcb.rules and pcb.rules[0]["NAME"] == "Clearance"


def test_binary_section_refused_loudly(tmp_path):
    streams = _cfbf.read_streams_qualified(_write_pcb(tmp_path))
    for section in ("Pads6", "Vias6", "Tracks6", "Arcs6", "Regions6"):
        with pytest.raises(AkcliError) as ei:
            altium_pcb.parse_ascii_section(streams, section)
        assert ei.value.code == "ALTIUM_MALFORMED"


def test_read_does_not_touch_binary_sections(tmp_path):
    # read() builds the model purely from ASCII sections; the present Pads6 binary
    # blob must not cause a failure (it is simply never parsed).
    pcb = altium_pcb.read(_write_pcb(tmp_path))
    assert pcb.nets and pcb.footprints


def test_export_stamps_schema_version(tmp_path):
    pcb = altium_pcb.read(_write_pcb(tmp_path))
    assert pcb.export()["schema_version"] == "1.0"
