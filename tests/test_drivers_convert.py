"""Fully-offline tests for the converter drivers (SPEC MS10 §2).

NO real binaries. The two seams are mocked:

* ``_binfetch.resolve`` -> a fake :class:`~pathlib.Path` (binary "present") or ``None``
  ("absent" -> graceful, never raises).
* ``run_subprocess`` -> a recorder capturing the EXACT argv and returning a fake
  ``CompletedProcess`` (returncode / stdout / stderr) so we can assert argv construction
  and the error-code mapping table without ever spawning a process.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from altium_kicad_cli.drivers import _binfetch, nlbn, npnp
from altium_kicad_cli.errors import AkcliError

FAKE_NLBN = Path("/fake/bin/nlbn")
FAKE_NPNP = Path("/fake/bin/npnp")


class Recorder:
    """Stand-in for ``safety.run_subprocess``; records argv, returns canned results.

    ``responses`` is a list of either ``(returncode, stdout_bytes, stderr_bytes)`` or a
    ``BaseException`` (raised to simulate a timeout). A single 3-tuple is reused for
    every call.
    """

    def __init__(self, responses) -> None:
        self.calls: list[list[str]] = []
        self._responses = responses
        self._i = 0

    def __call__(self, argv, timeout=None, maxout=None):
        self.calls.append(list(argv))
        resp = self._responses
        if isinstance(resp, list):
            resp = self._responses[min(self._i, len(self._responses) - 1)]
            self._i += 1
        if isinstance(resp, BaseException):
            raise resp
        rc, out, err = resp
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)


def _present(monkeypatch, tool: str, path: Path) -> None:
    monkeypatch.setattr(_binfetch, "resolve", lambda t, **kw: path if t == tool else None)


def _absent(monkeypatch) -> None:
    monkeypatch.setattr(_binfetch, "resolve", lambda t, **kw: None)


# --------------------------------------------------------------------------- #
# nlbn — available / version
# --------------------------------------------------------------------------- #
def test_nlbn_available(monkeypatch):
    _present(monkeypatch, "nlbn", FAKE_NLBN)
    assert nlbn.available() is True
    _absent(monkeypatch)
    assert nlbn.available() is False


def test_nlbn_version_parses_dotted_int(monkeypatch):
    _present(monkeypatch, "nlbn", FAKE_NLBN)
    rec = Recorder((0, b"nlbn 1.0.31\nUSAGE: ...", b""))
    monkeypatch.setattr(nlbn, "run_subprocess", rec)
    assert nlbn.version() == "1.0.31"
    # bare invocation, no subcommand
    assert rec.calls == [[str(FAKE_NLBN)]]


def test_nlbn_version_absent_is_none(monkeypatch):
    _absent(monkeypatch)
    assert nlbn.version() is None


# --------------------------------------------------------------------------- #
# nlbn — convert argv construction
# --------------------------------------------------------------------------- #
def test_nlbn_convert_no_3d_argv_and_success(monkeypatch, tmp_path):
    _present(monkeypatch, "nlbn", FAKE_NLBN)
    rec = Recorder((0, b"saved", b""))
    monkeypatch.setattr(nlbn, "run_subprocess", rec)

    out = tmp_path / "out"
    (out / "akcli.pretty").mkdir(parents=True)
    (out / "akcli.kicad_sym").write_text("(kicad_symbol_lib)")
    (out / "akcli.pretty" / "Foo.kicad_mod").write_text("(footprint)")

    res = nlbn.convert("C2040", out, with_3d=False)

    assert rec.calls == [[
        str(FAKE_NLBN), "--symbol", "--footprint",
        "--lcsc-id", "C2040", "-o", str(out), "--lib-name", "akcli",
    ]]
    assert res.ok is True
    assert res.available is True
    assert res.tool == "nlbn" and res.target == "kicad"
    assert res.lcsc_id == "C2040"
    assert res.exit_code == 0
    assert res.error_code is None
    names = {Path(a).name for a in res.artifacts}
    assert names == {"akcli.kicad_sym", "Foo.kicad_mod"}


def test_nlbn_convert_with_3d_uses_full(monkeypatch, tmp_path):
    _present(monkeypatch, "nlbn", FAKE_NLBN)
    rec = Recorder((0, b"", b""))
    monkeypatch.setattr(nlbn, "run_subprocess", rec)

    out = tmp_path / "out"
    (out / "akcli.3dshapes").mkdir(parents=True)
    (out / "akcli.kicad_sym").write_text("x")
    (out / "akcli.3dshapes" / "Foo.step").write_text("solid")

    res = nlbn.convert("c2040", out, with_3d=True)

    argv = rec.calls[0]
    assert "--full" in argv
    assert "--symbol" not in argv and "--footprint" not in argv
    assert res.with_3d is True and res.ok is True
    assert any(a.endswith("Foo.step") for a in res.artifacts)


def test_nlbn_convert_force_and_english(monkeypatch, tmp_path):
    _present(monkeypatch, "nlbn", FAKE_NLBN)
    rec = Recorder((0, b"", b""))
    monkeypatch.setattr(nlbn, "run_subprocess", rec)

    out = tmp_path / "out"
    out.mkdir()
    (out / "akcli.kicad_sym").write_text("x")

    nlbn.convert("C1", out, lib_name="mylib", force=True, lcsc_english=True)
    argv = rec.calls[0]
    assert "--overwrite" in argv
    assert "--lcsc-english" in argv
    assert "--lib-name" in argv and argv[argv.index("--lib-name") + 1] == "mylib"


# --------------------------------------------------------------------------- #
# nlbn — error mapping
# --------------------------------------------------------------------------- #
def test_nlbn_part_not_found(monkeypatch, tmp_path):
    _present(monkeypatch, "nlbn", FAKE_NLBN)
    rec = Recorder((1, b"", b"Error: no results found for keyword: C9"))
    monkeypatch.setattr(nlbn, "run_subprocess", rec)

    res = nlbn.convert("C9", tmp_path / "out")
    assert res.ok is False
    assert res.error_code == "CONVERT_PART_NOT_FOUND"
    assert res.exit_code == 1
    assert "no results found" in res.stderr


def test_nlbn_generic_failure(monkeypatch, tmp_path):
    _present(monkeypatch, "nlbn", FAKE_NLBN)
    rec = Recorder((1, b"", b"Error: network exploded"))
    monkeypatch.setattr(nlbn, "run_subprocess", rec)

    res = nlbn.convert("C2040", tmp_path / "out")
    assert res.ok is False
    assert res.error_code == "CONVERT_FAILED"


def test_nlbn_exit0_no_artifacts(monkeypatch, tmp_path):
    _present(monkeypatch, "nlbn", FAKE_NLBN)
    rec = Recorder((0, b"", b""))
    monkeypatch.setattr(nlbn, "run_subprocess", rec)

    res = nlbn.convert("C2040", tmp_path / "out")  # empty out dir
    assert res.ok is False
    assert res.error_code == "CONVERT_NO_ARTIFACTS"


def test_nlbn_timeout_is_structured_not_raised(monkeypatch, tmp_path):
    _present(monkeypatch, "nlbn", FAKE_NLBN)
    rec = Recorder(AkcliError("KICAD_CLI_TIMEOUT", "nlbn timed out after 180.0s"))
    monkeypatch.setattr(nlbn, "run_subprocess", rec)

    res = nlbn.convert("C2040", tmp_path / "out")
    assert res.ok is False
    assert res.available is True
    assert res.exit_code is None
    assert res.error_code == "KICAD_CLI_TIMEOUT"


def test_nlbn_absent_is_graceful(monkeypatch, tmp_path):
    _absent(monkeypatch)
    # run_subprocess must never be called when the binary is absent
    def _boom(*a, **k):  # pragma: no cover - asserts it isn't reached
        raise AssertionError("run_subprocess called for an absent binary")

    monkeypatch.setattr(nlbn, "run_subprocess", _boom)
    res = nlbn.convert("C2040", tmp_path / "out")
    assert res.available is False
    assert res.ok is False
    assert res.error_code == "KICAD_CLI_MISSING"
    assert res.exit_code is None


# --------------------------------------------------------------------------- #
# npnp — two-call argv + success
# --------------------------------------------------------------------------- #
def test_npnp_convert_runs_schlib_then_pcblib(monkeypatch, tmp_path):
    _present(monkeypatch, "npnp", FAKE_NPNP)
    rec = Recorder([(0, b"SchLib saved: a", b""), (0, b"PcbLib saved: b", b"")])
    monkeypatch.setattr(npnp, "run_subprocess", rec)

    out = tmp_path / "out"
    out.mkdir()
    (out / "Foo.SchLib").write_text("schlib")
    (out / "Foo.PcbLib").write_text("pcblib")

    res = npnp.convert("C2040", out, with_3d=True)

    assert rec.calls == [
        [str(FAKE_NPNP), "export-schlib", "C2040", "--index", "1", "--output", str(out)],
        [str(FAKE_NPNP), "export-pcblib", "C2040", "--index", "1", "--output", str(out)],
    ]
    assert res.ok is True
    assert res.tool == "npnp" and res.target == "altium"
    assert res.exit_code == 0
    names = {Path(a).name for a in res.artifacts}
    assert names == {"Foo.SchLib", "Foo.PcbLib"}


def test_npnp_force_and_english_flags(monkeypatch, tmp_path):
    _present(monkeypatch, "npnp", FAKE_NPNP)
    rec = Recorder([(0, b"", b""), (0, b"", b"")])
    monkeypatch.setattr(npnp, "run_subprocess", rec)

    out = tmp_path / "out"
    out.mkdir()
    (out / "Foo.SchLib").write_text("x")

    npnp.convert("C1", out, force=True, lcsc_english=True)
    assert "--lcsc-english" in rec.calls[0]
    assert "--force" in rec.calls[0]
    assert "--force" in rec.calls[1]
    # --lcsc-english is a schlib-only flag (not on export-pcblib)
    assert "--lcsc-english" not in rec.calls[1]


def test_npnp_first_call_failure_stops_and_maps(monkeypatch, tmp_path):
    _present(monkeypatch, "npnp", FAKE_NPNP)
    rec = Recorder([(2, b"", b"Error: no results found"), (0, b"", b"")])
    monkeypatch.setattr(npnp, "run_subprocess", rec)

    res = npnp.convert("C9", tmp_path / "out")
    # second subcommand is not attempted after the first fails
    assert len(rec.calls) == 1
    assert res.ok is False
    assert res.error_code == "CONVERT_PART_NOT_FOUND"
    assert res.exit_code == 2


def test_npnp_absent_is_graceful(monkeypatch, tmp_path):
    _absent(monkeypatch)

    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("run_subprocess called for an absent binary")

    monkeypatch.setattr(npnp, "run_subprocess", _boom)
    res = npnp.convert("C2040", tmp_path / "out")
    assert res.available is False
    assert res.error_code == "KICAD_CLI_MISSING"


def test_npnp_timeout_structured(monkeypatch, tmp_path):
    _present(monkeypatch, "npnp", FAKE_NPNP)
    rec = Recorder(AkcliError("KICAD_CLI_TIMEOUT", "npnp timed out"))
    monkeypatch.setattr(npnp, "run_subprocess", rec)

    res = npnp.convert("C2040", tmp_path / "out")
    assert res.available is True
    assert res.error_code == "KICAD_CLI_TIMEOUT"
    assert res.exit_code is None


# --------------------------------------------------------------------------- #
# ConvertResult serialization
# --------------------------------------------------------------------------- #
def test_convert_result_to_dict(monkeypatch, tmp_path):
    _present(monkeypatch, "nlbn", FAKE_NLBN)
    rec = Recorder((0, b"", b""))
    monkeypatch.setattr(nlbn, "run_subprocess", rec)
    out = tmp_path / "out"
    out.mkdir()
    (out / "akcli.kicad_sym").write_text("x")

    d = nlbn.convert("C2040", out).to_dict()
    assert d["ok"] is True
    assert d["tool"] == "nlbn"
    assert set(d) >= {
        "ok", "tool", "target", "lcsc_id", "out_dir", "artifacts",
        "with_3d", "exit_code", "available", "stderr", "error_code",
    }
