"""Fully-offline tests for ``akcli jlc add`` (SPEC MS10 §4).

NO real binaries, NO network. The seams are mocked:

* the driver module's ``convert`` (``drivers.nlbn`` / ``drivers.npnp``) -> a fake that
  optionally writes artifact files into ``--out`` and returns a :class:`ConvertResult`;
* ``parts.easyeda.lookup`` -> a fake (or ``None``) so the advisory metadata step never
  touches the network.

We assert exit codes for each outcome, the graceful install-hint on an absent binary,
the mandatory verify caveat, the ``--place`` op-list emission, and ``--json`` shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from altium_kicad_cli.cli import main
from altium_kicad_cli.drivers._convert import ConvertResult
from altium_kicad_cli.parts import easyeda as ee

_SYM = (
    '(kicad_symbol_lib (version 20211014) (generator akcli)'
    '  (symbol "RP2040" (in_bom yes) (on_board yes)'
    '    (property "Reference" "U" (id 0) (at 0 0 0))'
    '    (property "Value" "RP2040" (id 1) (at 0 0 0))'
    "  )"
    ")"
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Default: EasyEDA lookup returns nothing (never hits the network)."""
    monkeypatch.setattr(ee, "lookup", lambda *a, **k: None)


def _patch_convert(monkeypatch, target, fn):
    mod = "altium_kicad_cli.drivers." + ("nlbn" if target == "kicad" else "npnp")
    monkeypatch.setattr(mod + ".convert", fn)


def _ok_result(lcsc, out, *, tool, target, artifacts, with_3d=False):
    return ConvertResult(
        ok=True, tool=tool, target=target, lcsc_id=lcsc, out_dir=str(out),
        artifacts=[str(Path(a).resolve()) for a in artifacts],
        with_3d=with_3d, exit_code=0, available=True, stderr="", error_code=None,
    )


def _fail_result(lcsc, out, *, tool, target, error_code, stderr="", available=True):
    return ConvertResult(
        ok=False, tool=tool, target=target, lcsc_id=lcsc, out_dir=str(out),
        artifacts=[], with_3d=False, exit_code=(None if not available else 1),
        available=available, stderr=stderr, error_code=error_code,
    )


def _make_kicad_artifacts(out, *, lib_name="akcli", fp_name="RP2040_QFN56"):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    sym = out / f"{lib_name}.kicad_sym"
    sym.write_text(_SYM, encoding="utf-8")
    pretty = out / f"{lib_name}.pretty"
    pretty.mkdir(exist_ok=True)
    mod = pretty / f"{fp_name}.kicad_mod"
    mod.write_text("(footprint)", encoding="utf-8")
    return [sym, mod]


# --------------------------------------------------------------------------- #
# success
# --------------------------------------------------------------------------- #
def test_add_kicad_success_prints_artifacts_and_caveat(monkeypatch, tmp_path, capsys):
    out = tmp_path / "lib"

    def fake(lcsc, out_dir, **kw):
        arts = _make_kicad_artifacts(out_dir, lib_name=kw.get("lib_name", "akcli"))
        return _ok_result(lcsc, out_dir, tool="nlbn", target="kicad", artifacts=arts)

    _patch_convert(monkeypatch, "kicad", fake)
    rc = main(["jlc", "add", "C2040", "--to", "kicad", "--out", str(out)])
    cap = capsys.readouterr()
    assert rc == 0
    assert "akcli.kicad_sym" in cap.out
    assert "Verify pin mapping" in cap.out  # the mandatory verify caveat


def test_add_passes_flags_to_convert(monkeypatch, tmp_path):
    calls = []

    def fake(lcsc, out_dir, **kw):
        calls.append((lcsc, str(out_dir), kw))
        arts = _make_kicad_artifacts(out_dir, lib_name=kw.get("lib_name", "akcli"))
        return _ok_result(lcsc, out_dir, tool="nlbn", target="kicad", artifacts=arts,
                          with_3d=kw.get("with_3d", False))

    _patch_convert(monkeypatch, "kicad", fake)
    rc = main([
        "jlc", "add", "2040", "--to", "kicad", "--out", str(tmp_path / "o"),
        "--3d", "--force", "--english", "--lib-name", "mylib", "--auto-download",
    ])
    assert rc == 0
    lcsc, _, kw = calls[0]
    assert lcsc == "C2040"          # normalized from bare digits
    assert kw["with_3d"] is True
    assert kw["force"] is True
    assert kw["lcsc_english"] is True
    assert kw["lib_name"] == "mylib"
    assert kw["auto"] is True


def test_add_json_carries_result_and_note(monkeypatch, tmp_path, capsys):
    def fake(lcsc, out_dir, **kw):
        arts = _make_kicad_artifacts(out_dir)
        return _ok_result(lcsc, out_dir, tool="nlbn", target="kicad", artifacts=arts)

    _patch_convert(monkeypatch, "kicad", fake)
    rc = main(["jlc", "add", "C2040", "--to", "kicad", "--out", str(tmp_path / "o"), "--json"])
    cap = capsys.readouterr()
    assert rc == 0
    payload = json.loads(cap.out)
    assert payload["ok"] is True
    assert payload["tool"] == "nlbn"
    assert "Verify pin mapping" in payload["note"]


# --------------------------------------------------------------------------- #
# graceful degrade: binary absent -> install hint + exit 7, no auto-download
# --------------------------------------------------------------------------- #
def test_add_binary_absent_prints_hint_exit7(monkeypatch, tmp_path, capsys):
    def fake(lcsc, out_dir, **kw):
        assert kw["auto"] is False  # default: never auto-download
        return _fail_result(lcsc, out_dir, tool="nlbn", target="kicad",
                            error_code="KICAD_CLI_MISSING", available=False)

    _patch_convert(monkeypatch, "kicad", fake)
    rc = main(["jlc", "add", "C2040", "--to", "kicad", "--out", str(tmp_path / "o")])
    cap = capsys.readouterr()
    assert rc == 7
    assert "nlbn" in cap.err  # the copy-pasteable install hint


def test_add_npnp_absent_prints_hint_exit7(monkeypatch, tmp_path, capsys):
    def fake(lcsc, out_dir, **kw):
        return _fail_result(lcsc, out_dir, tool="npnp", target="altium",
                            error_code="KICAD_CLI_MISSING", available=False)

    _patch_convert(monkeypatch, "altium", fake)
    rc = main(["jlc", "add", "C2040", "--to", "altium", "--out", str(tmp_path / "o")])
    cap = capsys.readouterr()
    assert rc == 7
    assert "npnp" in cap.err


# --------------------------------------------------------------------------- #
# error mapping -> exit codes (SPEC §4.3)
# --------------------------------------------------------------------------- #
def test_add_part_not_found_exit4(monkeypatch, tmp_path, capsys):
    def fake(lcsc, out_dir, **kw):
        return _fail_result(lcsc, out_dir, tool="nlbn", target="kicad",
                            error_code="CONVERT_PART_NOT_FOUND",
                            stderr="Error: no results found for keyword: C9")

    _patch_convert(monkeypatch, "kicad", fake)
    rc = main(["jlc", "add", "C9", "--to", "kicad", "--out", str(tmp_path / "o")])
    cap = capsys.readouterr()
    assert rc == 4
    assert "CONVERT_PART_NOT_FOUND" in cap.err
    assert "no results found" in cap.err


def test_add_convert_failed_exit6(monkeypatch, tmp_path):
    def fake(lcsc, out_dir, **kw):
        return _fail_result(lcsc, out_dir, tool="nlbn", target="kicad",
                            error_code="CONVERT_FAILED", stderr="Error: boom")

    _patch_convert(monkeypatch, "kicad", fake)
    rc = main(["jlc", "add", "C2040", "--to", "kicad", "--out", str(tmp_path / "o")])
    assert rc == 6


def test_add_no_artifacts_exit6(monkeypatch, tmp_path):
    def fake(lcsc, out_dir, **kw):
        return _fail_result(lcsc, out_dir, tool="nlbn", target="kicad",
                            error_code="CONVERT_NO_ARTIFACTS")

    _patch_convert(monkeypatch, "kicad", fake)
    rc = main(["jlc", "add", "C2040", "--to", "kicad", "--out", str(tmp_path / "o")])
    assert rc == 6


# --------------------------------------------------------------------------- #
# --place op emission (KiCad only)
# --------------------------------------------------------------------------- #
def test_add_place_emits_place_component_op(monkeypatch, tmp_path, capsys):
    out = tmp_path / "o"

    def fake(lcsc, out_dir, **kw):
        arts = _make_kicad_artifacts(out_dir, fp_name="RP2040_QFN56")
        return _ok_result(lcsc, out_dir, tool="nlbn", target="kicad", artifacts=arts)

    _patch_convert(monkeypatch, "kicad", fake)
    # easyeda provides a value (MPN)
    monkeypatch.setattr(
        ee, "lookup",
        lambda *a, **k: ee.EasyEdaInfo(lcsc="C2040", mpn="RP2040", title="RP2040"),
    )
    rc = main([
        "jlc", "add", "C2040", "--to", "kicad", "--out", str(out),
        "--place", "--designator", "U1", "--at", "100", "200",
    ])
    assert rc == 0

    place = json.loads((out / "place.json").read_text())
    assert place["protocol_version"] == 1
    assert place["target_format"] == "kicad"
    assert len(place["ops"]) == 1
    op = place["ops"][0]
    assert op["op"] == "place_component"
    # lib_id symbol name is read from the produced .kicad_sym, NOT guessed from a filename
    assert op["lib_id"] == "akcli:RP2040"
    assert op["footprint"] == "akcli:RP2040_QFN56"
    assert op["designator"] == "U1"
    assert op["x_mil"] == 100 and op["y_mil"] == 200
    assert op["value"] == "RP2040"

    # the op-list also rides along in --json output
    capsys.readouterr()  # drain


def test_add_place_in_json_payload(monkeypatch, tmp_path, capsys):
    out = tmp_path / "o"

    def fake(lcsc, out_dir, **kw):
        arts = _make_kicad_artifacts(out_dir)
        return _ok_result(lcsc, out_dir, tool="nlbn", target="kicad", artifacts=arts)

    _patch_convert(monkeypatch, "kicad", fake)
    rc = main([
        "jlc", "add", "C2040", "--to", "kicad", "--out", str(out), "--json",
        "--place", "--designator", "U1", "--at", "10", "20",
    ])
    cap = capsys.readouterr()
    assert rc == 0
    payload = json.loads(cap.out)
    assert payload["place"]["ops"][0]["op"] == "place_component"


def test_add_altium_with_place_is_usage_error(monkeypatch, tmp_path):
    # convert must NOT be reached: the usage check fires first.
    def boom(*a, **k):  # pragma: no cover
        raise AssertionError("convert should not run on a usage error")

    _patch_convert(monkeypatch, "altium", boom)
    rc = main([
        "jlc", "add", "C2040", "--to", "altium",
        "--place", "--designator", "U1", "--at", "1", "2",
    ])
    assert rc == 2


def test_add_place_without_designator_is_usage_error(monkeypatch):
    def boom(*a, **k):  # pragma: no cover
        raise AssertionError("convert should not run on a usage error")

    _patch_convert(monkeypatch, "kicad", boom)
    rc = main(["jlc", "add", "C2040", "--to", "kicad", "--place", "--at", "1", "2"])
    assert rc == 2


def test_add_place_without_at_is_usage_error(monkeypatch):
    def boom(*a, **k):  # pragma: no cover
        raise AssertionError("convert should not run on a usage error")

    _patch_convert(monkeypatch, "kicad", boom)
    rc = main(["jlc", "add", "C2040", "--to", "kicad", "--place", "--designator", "U1"])
    assert rc == 2


# --------------------------------------------------------------------------- #
# misc usage / advisory behaviour
# --------------------------------------------------------------------------- #
def test_add_missing_to_is_argparse_error(monkeypatch):
    with pytest.raises(SystemExit) as ei:
        main(["jlc", "add", "C2040"])
    assert ei.value.code == 2


def test_add_empty_lcsc_is_usage_error(monkeypatch):
    rc = main(["jlc", "add", "", "--to", "kicad"])
    assert rc == 2


def test_add_3d_warns_when_no_3d_available(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        ee, "lookup",
        lambda *a, **k: ee.EasyEdaInfo(lcsc="C2040", has_3d=False),
    )

    def fake(lcsc, out_dir, **kw):
        assert kw["with_3d"] is True  # still requested despite the warning
        arts = _make_kicad_artifacts(out_dir)
        return _ok_result(lcsc, out_dir, tool="nlbn", target="kicad", artifacts=arts,
                          with_3d=True)

    _patch_convert(monkeypatch, "kicad", fake)
    rc = main(["jlc", "add", "C2040", "--to", "kicad", "--out", str(tmp_path / "o"), "--3d"])
    cap = capsys.readouterr()
    assert rc == 0
    assert "no 3D model" in cap.err
