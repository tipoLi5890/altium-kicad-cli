"""Tests for :mod:`altium_kicad_cli.writers.lib_cache` (SPEC §3.5).

Covers caching a plain symbol, dedup/idempotency, requalification of the parent
name with unqualified child-unit names, full pin-electrical-type preservation,
the ``C_Polarized`` ``(extends "C")`` base-copy case, sourcing from both a
``.kicad_sym`` library and a template ``.kicad_sch``, creating a missing
``lib_symbols`` node, ``SYMBOL_NOT_FOUND`` on a miss, and round-trip
serializability of the mutated document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from altium_kicad_cli import model
from altium_kicad_cli.errors import AkcliError
from altium_kicad_cli.readers import kicad_lib, sexpr
from altium_kicad_cli.readers.sexpr import SNode
from altium_kicad_cli.writers import lib_cache

FIX = Path(__file__).parent / "fixtures" / "kicad"
DEVICE = FIX / "symbols" / "Device.kicad_sym"
POWER = FIX / "symbols" / "power.kicad_sym"
BOARD_V8 = FIX / "board_v8.kicad_sch"

# A minimal document WITH an empty lib_symbols node.
_DOC_WITH_LIBSYMS = (
    "(kicad_sch\n"
    '\t(version 20231120)\n'
    '\t(generator "eeschema")\n'
    '\t(uuid "00000000-0000-4000-8000-000000000000")\n'
    '\t(paper "A4")\n'
    "\t(lib_symbols)\n"
    "\t(symbol\n"
    '\t\t(lib_id "Device:R")\n'
    '\t\t(at 100 100 0))\n'
    ")\n"
)

# A minimal document WITHOUT any lib_symbols node.
_DOC_NO_LIBSYMS = (
    "(kicad_sch\n"
    '\t(version 20231120)\n'
    '\t(generator "eeschema")\n'
    '\t(uuid "00000000-0000-4000-8000-000000000000")\n'
    '\t(paper "A4")\n'
    "\t(symbol\n"
    '\t\t(lib_id "Device:R")\n'
    '\t\t(at 100 100 0))\n'
    ")\n"
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _doc(text: str = _DOC_WITH_LIBSYMS) -> SNode:
    return sexpr.parse(text)


def _libsyms(doc: SNode) -> SNode:
    node = doc.find("lib_symbols")
    assert node is not None
    return node


def _symbol_names(libsyms: SNode) -> list[str]:
    return [s.children[1].value for s in libsyms.find_all("symbol")]


def _cached_symbol(libsyms: SNode, name: str) -> SNode:
    for s in libsyms.find_all("symbol"):
        if s.children[1].value == name:
            return s
    raise AssertionError(f"{name!r} not cached; have {_symbol_names(libsyms)}")


def _pin_types(sym: SNode) -> list[str]:
    """Electrical-type tokens of every (pin <type> ...) descendant of ``sym``."""
    types: list[str] = []
    stack: list = [iter(sym.children or [])]
    while stack:
        try:
            nd = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if not nd.is_list:
            continue
        if nd.tag == "pin":
            after = [c.value for c in nd.children[1:] if c.is_atom]
            if after:
                types.append(after[0])
        elif nd.tag == "symbol":
            stack.append(iter(nd.children or []))
    return types


def _reparse(doc: SNode) -> SNode:
    """Serialize then re-parse the mutated document (proves it round-trips)."""
    return sexpr.parse(sexpr.dumps(doc))


# --------------------------------------------------------------------------- #
# plain caching
# --------------------------------------------------------------------------- #
def test_cache_plain_symbol_adds_qualified_entry():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    libsyms = _libsyms(doc)
    assert "Device:R" in _symbol_names(libsyms)


def test_cached_symbol_keeps_full_pin_electrical_types():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    sym = _cached_symbol(_libsyms(doc), "Device:R")
    # R has two passive pins; ERC depends on these tokens surviving the copy.
    assert _pin_types(sym) == ["passive", "passive"]


def test_child_unit_names_stay_unqualified():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    sym = _cached_symbol(_libsyms(doc), "Device:R")
    child_unit_names = {s.children[1].value for s in sym.find_all("symbol")}
    # Parent is requalified Device:R; unit sub-symbols stay unqualified.
    assert child_unit_names == {"R_0_1", "R_1_1"}
    assert all(":" not in n for n in child_unit_names)


def test_power_symbol_pin_type_preserved():
    doc = _doc()
    lib_cache.ensure_cached(doc, "power:GND", [POWER])
    sym = _cached_symbol(_libsyms(doc), "power:GND")
    assert _pin_types(sym) == ["power_in"]


# --------------------------------------------------------------------------- #
# dedup / idempotency
# --------------------------------------------------------------------------- #
def test_dedup_same_lib_id_called_twice():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    assert _symbol_names(_libsyms(doc)).count("Device:R") == 1


def test_idempotent_serialization():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    first = sexpr.dumps(doc)
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    assert sexpr.dumps(doc) == first


def test_does_not_duplicate_preexisting_cache_entry():
    # Pre-seed lib_symbols with a Device:R, then ensure_cached should no-op it.
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    names_before = _symbol_names(_libsyms(doc))
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    assert _symbol_names(_libsyms(doc)) == names_before


# --------------------------------------------------------------------------- #
# extends (C_Polarized) — base must be copied too
# --------------------------------------------------------------------------- #
def test_extends_caches_both_derived_and_base():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:C_Polarized", [DEVICE])
    names = _symbol_names(_libsyms(doc))
    assert "Device:C_Polarized" in names
    assert "Device:C" in names  # base resolved + copied


def test_extends_reference_stays_unqualified():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:C_Polarized", [DEVICE])
    derived = _cached_symbol(_libsyms(doc), "Device:C_Polarized")
    ext = derived.find("extends")
    assert ext is not None
    # KiCad stores the base reference unqualified; the cached base is Device:C.
    assert ext.children[1].value == "C"


def test_extends_base_carries_the_pins():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:C_Polarized", [DEVICE])
    base = _cached_symbol(_libsyms(doc), "Device:C")
    # The derived symbol has no pins of its own; the base supplies them.
    assert _pin_types(base) == ["passive", "passive"]


def test_extends_child_units_unqualified():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:C_Polarized", [DEVICE])
    derived = _cached_symbol(_libsyms(doc), "Device:C_Polarized")
    child_unit_names = {s.children[1].value for s in derived.find_all("symbol")}
    assert child_unit_names == {"C_Polarized_0_1"}


# --------------------------------------------------------------------------- #
# source coercion: Library object, template .kicad_sch
# --------------------------------------------------------------------------- #
def test_source_as_library_object():
    lib = kicad_lib.read(DEVICE)
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:R", [lib])
    assert "Device:R" in _symbol_names(_libsyms(doc))


def test_source_as_template_kicad_sch():
    doc = _doc()
    # board_v8.kicad_sch's inline lib_symbols defines Device:R / Device:C.
    lib_cache.ensure_cached(doc, "Device:R", [BOARD_V8])
    assert "Device:R" in _symbol_names(_libsyms(doc))


def test_single_source_not_in_a_list():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:R", DEVICE)  # bare path, no list
    assert "Device:R" in _symbol_names(_libsyms(doc))


# --------------------------------------------------------------------------- #
# missing lib_symbols node is created
# --------------------------------------------------------------------------- #
def test_creates_lib_symbols_when_absent():
    doc = _doc(_DOC_NO_LIBSYMS)
    assert doc.find("lib_symbols") is None
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    libsyms = doc.find("lib_symbols")
    assert libsyms is not None
    assert "Device:R" in _symbol_names(libsyms)


def test_created_lib_symbols_precedes_symbol_instance():
    doc = _doc(_DOC_NO_LIBSYMS)
    lib_cache.ensure_cached(doc, "Device:R", [DEVICE])
    tags = [c.tag for c in doc.children if c.is_list]
    assert "lib_symbols" in tags and "symbol" in tags
    assert tags.index("lib_symbols") < tags.index("symbol")


# --------------------------------------------------------------------------- #
# round-trip / serialization integrity
# --------------------------------------------------------------------------- #
def test_mutated_doc_reparses_with_symbol_present():
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:C_Polarized", [DEVICE])
    re = _reparse(doc)
    names = _symbol_names(_libsyms(re))
    assert {"Device:C_Polarized", "Device:C"} <= set(names)


def test_source_library_node_not_mutated():
    # Caching must deep-copy: the source Library's body must keep its own name.
    lib = kicad_lib.read(DEVICE)
    doc = _doc()
    lib_cache.ensure_cached(doc, "Device:R", [lib])
    src_r = next(s for s in lib.symbols if s.name == "R")
    assert src_r.body_sexpr.children[1].value == "R"  # untouched, not "Device:R"


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #
def test_missing_symbol_raises_symbol_not_found():
    doc = _doc()
    with pytest.raises(AkcliError) as ei:
        lib_cache.ensure_cached(doc, "Device:DoesNotExist", [DEVICE])
    assert ei.value.code == "SYMBOL_NOT_FOUND"


def test_empty_sources_raises_symbol_not_found():
    doc = _doc()
    with pytest.raises(AkcliError) as ei:
        lib_cache.ensure_cached(doc, "Device:R", [])
    assert ei.value.code == "SYMBOL_NOT_FOUND"


def test_unqualified_lib_id_caches_unqualified():
    doc = _doc()
    lib_cache.ensure_cached(doc, "R", [DEVICE])
    assert "R" in _symbol_names(_libsyms(doc))
