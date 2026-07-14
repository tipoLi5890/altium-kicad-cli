"""Shared test isolation.

The `jlc` family caches HTTP responses under the user's cache directory by
default; tests must neither READ a developer's warm cache (a mocked-offline
test would silently pass on cached data) nor WRITE junk into it.

Tests are also hermetic: the default opener factories of both networked
modules are replaced with one that raises, so any test that would touch the
real network fails loudly and attributably instead of flaking (or silently
passing against live data). Tests inject an ``opener=`` or monkeypatch
``_default_opener`` themselves — a per-test monkeypatch simply overrides the
guard.
"""

from __future__ import annotations

import pytest

from akcli.parts import easyeda as _easyeda
from akcli.parts import search as _search


@pytest.fixture(autouse=True)
def _no_jlc_cache(monkeypatch):
    monkeypatch.setenv("AKCLI_JLC_CACHE", "off")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _blocked():
        raise RuntimeError(
            "network disabled in tests: pass opener=... or monkeypatch "
            "_default_opener on parts.search / parts.easyeda")

    monkeypatch.setattr(_search, "_default_opener", _blocked)
    monkeypatch.setattr(_easyeda, "_default_opener", _blocked)


@pytest.fixture(scope="session")
def _kicad_global_cfg(tmp_path_factory) -> str:
    """A minimal, controlled KiCad global lib-table (a few standard nicknames).

    Keeps ``library audit`` hermetic: tests neither read the developer's real
    ``~/.../kicad`` config nor behave differently on CI, while still exercising
    the project → global nickname resolution path.
    """
    cfg = tmp_path_factory.mktemp("kicad_cfg")
    (cfg / "sym-lib-table").write_text(
        '(sym_lib_table (version 7)\n'
        '  (lib (name "Device")(type "KiCad")(uri "Device.kicad_sym")(options "")(descr ""))\n'
        '  (lib (name "power")(type "KiCad")(uri "power.kicad_sym")(options "")(descr ""))\n'
        '  (lib (name "Connector")(type "KiCad")(uri "Connector.kicad_sym")(options "")(descr ""))\n'
        ')\n', encoding="utf-8")
    (cfg / "fp-lib-table").write_text(
        '(fp_lib_table (version 7)\n'
        '  (lib (name "Resistor_SMD")(type "KiCad")(uri "Resistor_SMD.pretty")(options "")(descr ""))\n'
        '  (lib (name "Connector")(type "KiCad")(uri "Connector.pretty")(options "")(descr ""))\n'
        '  (lib (name "TestPoint")(type "KiCad")(uri "TestPoint.pretty")(options "")(descr ""))\n'
        ')\n', encoding="utf-8")
    return str(cfg)


@pytest.fixture(autouse=True)
def _isolate_kicad_config(monkeypatch, _kicad_global_cfg):
    monkeypatch.setenv("KICAD_CONFIG_HOME", _kicad_global_cfg)
