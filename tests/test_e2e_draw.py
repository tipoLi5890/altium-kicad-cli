"""End-to-end coverage for the KiCad write/draw half.

The round-trip test (draw an op-list -> re-read the written file) runs everywhere.
The ``kicad-cli`` test only runs where a real KiCad is installed (the CI KiCad job),
and confirms KiCad itself accepts the schematic ``akcli`` produced — closing the gap
that an Altium-only reviewer can't exercise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from altium_kicad_cli.drivers import kicad_cli
from altium_kicad_cli.readers import kicad as kreader
from altium_kicad_cli.writers import kicad as kw

V8 = Path(__file__).parent / "fixtures" / "kicad" / "board_v8.kicad_sch"


def _oplist(*ops):
    return {"protocol_version": 1, "target_format": "kicad", "ops": list(ops)}


def _seed(tmp_path: Path) -> Path:
    tgt = tmp_path / "board.kicad_sch"
    tgt.write_bytes(V8.read_bytes())
    return tgt


def test_draw_then_reread_roundtrip(tmp_path):
    """draw -> apply -> re-read: the placed part is present and the file re-parses."""
    tgt = _seed(tmp_path)
    results = kw.apply(
        _oplist({"op": "place_component", "lib_id": "Device:C",
                 "designator": "C99", "x_mil": 4000, "y_mil": 4000, "value": "100n"}),
        str(tgt), apply=True,
    )
    assert all(r.status == "ok" for r in results)

    sch = kreader.read_sch(str(tgt))
    assert "C99" in {c.designator for c in sch.components}


def test_drawn_file_accepted_by_kicad_cli(tmp_path):
    """A real ``kicad-cli`` (CI KiCad job) must accept the file akcli wrote."""
    if not kicad_cli.available():
        pytest.skip("kicad-cli not installed (runs in the CI KiCad job)")
    tgt = _seed(tmp_path)
    kw.apply(
        _oplist({"op": "place_component", "lib_id": "Device:R",
                 "designator": "R99", "x_mil": 5000, "y_mil": 5000, "value": "10k"}),
        str(tgt), apply=True,
    )
    # KiCad's own ERC must parse the file we wrote (returns a report dict, not a crash).
    report = kicad_cli.erc(str(tgt))
    assert report is not None
