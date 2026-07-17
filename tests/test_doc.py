"""`akcli doc` — the pinout book (pin tables + power rails + BOM).

The book is the human hand-off for agent-drawn schematics: per-component
pin-to-net tables, the `review tree` rail summary, and a grouped BOM, all
deterministic Markdown (no timestamps; same input bytes -> same output bytes).
"""

from __future__ import annotations

import json
from pathlib import Path

from akcli.cli import main
from akcli.errors import EXIT

FIXTURES = Path(__file__).parent / "fixtures"
BOARD = FIXTURES / "corpus" / "analog_frontend.kicad_sch"


def _doc(capsys, *argv: str) -> str:
    assert main(["doc", str(BOARD), *argv]) == EXIT["OK"]
    return capsys.readouterr().out


def test_pin_tables_show_the_as_drawn_nets(capsys):
    out = _doc(capsys, "--refs", "R*,C*,L*")
    assert "# analog_frontend.kicad_sch — pinout book" in out
    # a pin row carries the net the pin actually landed on
    assert "### R1 — 10k (Device:R)" in out
    assert "| 1 | ~ | passive | 3V3 |" in out
    assert "| Pin | Name | Type | Net |" in out


def test_default_refs_note_when_nothing_matches(capsys):
    # the corpus board has no U*/J* parts — the book says so instead of
    # silently emitting an empty section
    out = _doc(capsys)
    assert "no components match" in out


def test_rails_and_bom_sections(capsys):
    out = _doc(capsys, "--refs", "R*")
    assert "## Power rails" in out
    assert "| 3V3 | 3.3 V |" in out
    assert "## BOM" in out
    # grouped by value/symbol/footprint, refs natural-sorted
    assert "| 2 | R1, R2 | 10k |" in out


def test_output_is_deterministic(capsys):
    a = _doc(capsys, "--refs", "R*,C*")
    b = _doc(capsys, "--refs", "R*,C*")
    assert a == b


def test_out_file_is_lf_only_utf8(tmp_path, capsys):
    out = tmp_path / "book.md"
    assert main(["doc", str(BOARD), "-o", str(out), "--refs", "R*"]) == EXIT["OK"]
    data = out.read_bytes()
    assert b"\r\n" not in data
    assert "pinout book" in data.decode("utf-8")
    # stdout stays clean when -o is used (stdout = data convention)
    assert capsys.readouterr().out == ""


def test_json_payload(capsys):
    assert main(["doc", str(BOARD), "--json", "--refs", "R*,L*"]) == EXIT["OK"]
    doc = json.loads(capsys.readouterr().out)
    assert doc["schema_version"]
    assert doc["source"].endswith("analog_frontend.kicad_sch")
    refs = [c["ref"] for c in doc["components"]]
    assert refs == sorted(refs, key=lambda r: (r[0], int(r[1:])))
    r1 = next(c for c in doc["components"] if c["ref"] == "R1")
    assert {"number": "1", "name": "~", "type": "passive", "net": "3V3"} \
        in r1["pins"]
    assert any(r["net"] == "3V3" and r["voltage"] == 3.3 for r in doc["rails"])
    assert any(row["qty"] == 2 and row["refs"] == ["R1", "R2"]
               for row in doc["bom"])


def test_non_schematic_is_unsupported(tmp_path, capsys):
    bad = tmp_path / "x.txt"
    bad.write_text("hello", encoding="utf-8")
    assert main(["doc", str(bad)]) == EXIT["UNSUPPORTED_FORMAT"]


def test_missing_file_is_not_found(tmp_path):
    assert main(["doc", str(tmp_path / "nope.kicad_sch")]) == EXIT["NOT_FOUND"]
