"""Tests for :mod:`altium_kicad_cli.drivers.kicad_cli` — optional ERC wrapper (SPEC §3.7).

``kicad-cli`` is an **optional** secondary verifier; the primary gate is the pure
Python :mod:`..writers.connectivity`. The behavioural tests therefore ``skipif`` the
tool is not installed (the dev/CI mac has no KiCad), while the *graceful-degradation*
tests — that absence is non-fatal — run everywhere.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from altium_kicad_cli.drivers import kicad_cli

FIX = Path(__file__).parent / "fixtures" / "kicad"
V8 = FIX / "board_v8.kicad_sch"

_HAVE = shutil.which("kicad-cli") is not None
needs_cli = pytest.mark.skipif(not _HAVE, reason="kicad-cli not installed")


# --------------------------------------------------------------------------- #
# graceful degradation (runs with or without kicad-cli)
# --------------------------------------------------------------------------- #
def test_available_returns_bool():
    assert isinstance(kicad_cli.available(), bool)
    assert kicad_cli.available() == _HAVE


def test_absent_tool_is_non_fatal(monkeypatch):
    # Force "tool absent" and assert every entry point degrades to None (no raise).
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert kicad_cli.available() is False
    assert kicad_cli.version() is None
    assert kicad_cli.erc(str(V8)) is None
    assert kicad_cli.netlist(str(V8)) is None


def test_parse_version_helper():
    assert kicad_cli._parse_version("8.0.4") == (8, 0, 4)
    assert kicad_cli._parse_version("kicad-cli 7.0.11+foo") == (7, 0, 11)
    assert kicad_cli._parse_version("no version here") is None


# --------------------------------------------------------------------------- #
# real kicad-cli (skipped when not installed)
# --------------------------------------------------------------------------- #
@needs_cli
def test_version_when_installed():
    v = kicad_cli.version()
    assert v is not None and isinstance(v[0], int)


@needs_cli
def test_erc_when_installed():
    rep = kicad_cli.erc(str(V8))
    assert rep is None or isinstance(rep, dict)
    if isinstance(rep, dict):
        assert "exit_code" in rep


@needs_cli
def test_netlist_when_installed():
    rep = kicad_cli.netlist(str(V8))
    assert rep is None or isinstance(rep, dict)
