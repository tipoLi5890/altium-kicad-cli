"""``lib_symbols`` cache resolution & copy for the KiCad writer (SPEC §3.5).

A ``.kicad_sch`` is self-contained: every symbol it instantiates is copied,
verbatim and **library-qualified**, into a top-level ``(lib_symbols ...)`` node.
A placed ``(symbol (lib_id "Device:R") ...)`` instance carries only pin numbers;
KiCad (and our ERC) reads the symbol's *electrical truth* — pin names, numbers
and **electrical types** — out of this cache. So before the executor can place a
component, the symbol must be present in ``lib_symbols``.

:func:`ensure_cached` is that step. For a requested ``lib_id`` (e.g.
``"Device:C_Polarized"``) it:

* locates the symbol across the configured *sources* (``.kicad_sym`` libraries
  and/or a template ``.kicad_sch``'s inline ``lib_symbols``) via
  :mod:`..readers.kicad_lib`, raising ``SYMBOL_NOT_FOUND`` on a miss;
* copies the raw ``(symbol ...)`` body (``SymbolDef.body_sexpr``) **deep**, so the
  source library node is never mutated and **full pin electrical types are
  preserved** (ERC needs them);
* **requalifies the parent symbol name** to ``Nick:Name`` (the instance's
  ``lib_id``) while keeping the child unit sub-symbol names unqualified
  (``Name_0_1`` / ``Name_1_1``) and any ``(extends "Base")`` reference unqualified;
* **resolves and copies an ``(extends ...)`` base** symbol too (KiCad caches both
  the derived part and its base, e.g. ``Device:C_Polarized`` + ``Device:C``);
* **dedups by qualified lib_id**: a symbol already present is left untouched, so
  ``ensure_cached`` is idempotent and safe to call once per placed component.

Geometry-free: this module only shuffles S-expression nodes; no coordinates are
touched. The serializer (``sexpr.dumps`` / the writer's ``sexpr_writer``) renders
the mutated ``doc`` back to text.
"""

from __future__ import annotations

import os
from pathlib import Path

from .. import model
from ..errors import fail
from ..readers import kicad_lib, sexpr
from ..readers.sexpr import SNode
from ..safety import MAX_FILE_BYTES

__all__ = ["ensure_cached"]

# Guard against a pathological / cyclic ``(extends ...)`` chain. Real chains are
# 1-2 deep; we follow at most this many hops before declaring the library bad.
_MAX_EXTENDS = 64

# Default whitespace used when synthesizing a fresh ``(lib_symbols ...)`` node or
# when a sibling-derived indent cannot be recovered (KiCad uses tab indentation).
_DOC_CHILD_WS = "\n\t"      # one level deep: a direct child of (kicad_sch ...)
_SYM_CHILD_WS = "\n\t\t"    # two levels deep: a (symbol ...) inside (lib_symbols ...)

# Tags that mark the start of a schematic's *body* (instances/graphics). A freshly
# created ``lib_symbols`` is inserted just before the first of these so it lands in
# its canonical position right after the header block.
_BODY_TAGS = frozenset(
    {
        "junction",
        "no_connect",
        "bus_entry",
        "wire",
        "bus",
        "polyline",
        "text",
        "label",
        "global_label",
        "hierarchical_label",
        "symbol",
        "sheet",
        "sheet_instances",
        "symbol_instances",
    }
)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def ensure_cached(
    doc: SNode,
    lib_id: str,
    sources: object,
) -> None:
    """Ensure ``lib_id`` (and any ``(extends)`` base) is present in ``doc``'s cache.

    ``doc`` is the parsed root :class:`SNode` of a ``.kicad_sch`` document; it is
    mutated in place (its ``(lib_symbols ...)`` node is created if absent and the
    resolved symbol(s) appended). ``sources`` is an iterable whose items are any
    mix of:

    * a :class:`model.Library` (already parsed),
    * a path to a ``.kicad_sym`` library file, or
    * a path to a template ``.kicad_sch`` (its inline ``lib_symbols`` is used).

    Raises ``SYMBOL_NOT_FOUND`` if ``lib_id`` (or an ``extends`` base) resolves in
    none of the sources. Idempotent: a symbol already cached is left untouched.
    """
    libs = _coerce_sources(sources)
    libsyms = _ensure_lib_symbols_node(doc)
    nick = _nick_of(lib_id)
    cached = _existing_names(libsyms)
    # The requested symbol keeps the instance's exact qualified id; bases are
    # requalified within the same nick (their (extends) ref is unqualified).
    _cache_symbol(libsyms, request=lib_id, qualified=lib_id, nick=nick, libs=libs, cached=cached)


# --------------------------------------------------------------------------- #
# Caching core
# --------------------------------------------------------------------------- #
def _cache_symbol(
    libsyms: SNode,
    request: str,
    qualified: str,
    nick: str | None,
    libs: list[model.Library],
    cached: set[str],
    _hops: int = 0,
) -> None:
    """Resolve ``request``, copy it as ``qualified``, then recurse into its base."""
    if qualified in cached:
        return  # already present (pre-existing or just added) -> dedup + cycle guard
    if _hops > _MAX_EXTENDS:
        fail("SYMBOL_NOT_FOUND", f"extends chain too deep resolving {request!r}")

    sym = _find_symbol(request, libs)
    if sym is None:
        fail("SYMBOL_NOT_FOUND", f"symbol {request!r} not found in any source library")
    if not isinstance(sym.body_sexpr, SNode):
        # Only KiCad-sourced SymbolDefs carry a raw body we can copy.
        fail("SYMBOL_NOT_FOUND", f"symbol {request!r} has no copyable KiCad body")

    body = _clone(sym.body_sexpr)
    _set_symbol_name(body, qualified)
    _append_symbol(libsyms, body)
    cached.add(qualified)

    if sym.extends:
        base_request = sym.extends                      # unqualified base name (kept as-is)
        base_qualified = _requalify(nick, sym.extends)  # cached under Nick:Base
        _cache_symbol(
            libsyms,
            request=base_request,
            qualified=base_qualified,
            nick=nick,
            libs=libs,
            cached=cached,
            _hops=_hops + 1,
        )


def _find_symbol(name: str, libs: list[model.Library]) -> model.SymbolDef | None:
    """Find a symbol by exact name/lib_id, falling back to an unqualified match.

    Mirrors :func:`kicad_lib._find_symbol` without depending on a private name:
    an exact pass matches ``Device:R`` or a fully qualified request; the fallback
    lets a bare ``(extends "C")`` resolve against a qualified ``Device:C`` entry
    and a qualified ``Device:R`` request resolve against an unqualified ``R`` lib.
    """
    for lib in libs:
        for s in lib.symbols:
            if s.name == name or s.lib_id == name:
                return s
    target = _unqual(name)
    for lib in libs:
        for s in lib.symbols:
            if _unqual(s.name) == target:
                return s
    return None


# --------------------------------------------------------------------------- #
# ``lib_symbols`` node management
# --------------------------------------------------------------------------- #
def _ensure_lib_symbols_node(doc: SNode) -> SNode:
    """Return ``doc``'s ``(lib_symbols ...)`` node, creating + inserting one if absent."""
    if not isinstance(doc, SNode) or doc.is_atom:
        fail("SYMBOL_NOT_FOUND", "document is not a parsed kicad_sch node")
    existing = doc.find("lib_symbols")
    if existing is not None:
        return existing

    # Fresh node: ``(lib_symbols\n\t)`` — head atom + a closing-paren indent so the
    # first appended symbol nests cleanly.
    node = SNode(False, children=[SNode.atom("lib_symbols")], ws=["", _DOC_CHILD_WS])
    _insert_doc_child(doc, node)
    return node


def _insert_doc_child(doc: SNode, node: SNode) -> None:
    """Insert ``node`` as a child of ``doc`` just before its body (instances/graphics)."""
    kids = doc.children or []
    indent = _doc_child_indent(doc)
    idx = len(kids)  # default: append before the closing paren
    for i, child in enumerate(kids):
        if child.is_list and child.tag in _BODY_TAGS:
            idx = i
            break
    kids.insert(idx, node)
    # ``ws[i]`` is the whitespace before ``children[i]``; inserting at ``idx`` pushes
    # the old ``ws[idx]`` (which belonged to the node now at ``idx+1``) along.
    doc.ws.insert(idx, indent)


def _append_symbol(libsyms: SNode, body: SNode) -> None:
    """Append a ``(symbol ...)`` ``body`` as the last child of ``libsyms``."""
    indent = _sym_child_indent(libsyms)
    libsyms.children.append(body)
    # Insert the new child's leading whitespace just before the closing-paren ws.
    libsyms.ws.insert(len(libsyms.ws) - 1, indent)


def _existing_names(libsyms: SNode) -> set[str]:
    """Set of qualified symbol names already cached in ``libsyms``."""
    out: set[str] = set()
    for s in libsyms.find_all("symbol"):
        nm = _symbol_name(s)
        if nm is not None:
            out.add(nm)
    return out


# --------------------------------------------------------------------------- #
# Node helpers
# --------------------------------------------------------------------------- #
def _symbol_name(sym: SNode) -> str | None:
    """Decoded name of a ``(symbol "Name" ...)`` node (its second child), or ``None``."""
    kids = sym.children or []
    if len(kids) >= 2 and kids[1].is_atom:
        return kids[1].value
    return None


def _set_symbol_name(sym: SNode, name: str) -> None:
    """Requalify a ``(symbol "Old" ...)`` node's name atom in place to ``name``."""
    kids = sym.children or []
    if len(kids) < 2 or not kids[1].is_atom:
        fail("SYMBOL_NOT_FOUND", "malformed symbol body (missing name atom)")
    kids[1].text = _quote(name)


def _doc_child_indent(doc: SNode) -> str:
    """Indentation of a direct child of the document (e.g. before ``(version ...)``)."""
    for w in (doc.ws or [])[:-1]:
        if "\n" in w:
            return w
    return _DOC_CHILD_WS


def _sym_child_indent(libsyms: SNode) -> str:
    """Indentation of a ``(symbol ...)`` child inside ``lib_symbols``.

    Recovered from an existing newline-bearing child whitespace (never the final
    closing-paren ws, which is one level shallower); falls back to two tabs.
    """
    for w in (libsyms.ws or [])[:-1]:
        if "\n" in w:
            return w
    return _SYM_CHILD_WS


# --------------------------------------------------------------------------- #
# Deep clone (iterative — no native recursion on attacker-influenced trees)
# --------------------------------------------------------------------------- #
def _clone(node: SNode) -> SNode:
    """Deep-copy an :class:`SNode` so the source library tree is never mutated."""
    if node.is_atom:
        return _clone_atom(node)
    root = _new_list(node)
    # Each stack frame pairs a source list node with its fresh copy; children are
    # appended in source order within each frame, so ordering is preserved.
    stack: list[tuple[SNode, SNode]] = [(node, root)]
    while stack:
        src, dst = stack.pop()
        for ch in src.children or []:
            if ch.is_atom:
                dst.children.append(_clone_atom(ch))
            else:
                copy = _new_list(ch)
                dst.children.append(copy)
                stack.append((ch, copy))
    return root


def _clone_atom(node: SNode) -> SNode:
    a = SNode.atom(node.text)
    a.prefix = node.prefix
    a.suffix = node.suffix
    return a


def _new_list(node: SNode) -> SNode:
    nl = SNode(False, children=[], ws=list(node.ws or []))
    nl.prefix = node.prefix
    nl.suffix = node.suffix
    return nl


# --------------------------------------------------------------------------- #
# Name / quoting helpers
# --------------------------------------------------------------------------- #
def _nick_of(lib_id: str) -> str | None:
    """Library nickname of ``Nick:Name`` (``None`` when ``lib_id`` has no nick)."""
    return lib_id.split(":", 1)[0] if ":" in lib_id else None


def _unqual(name: str | None) -> str:
    """Library-unqualified symbol name (``Device:R`` -> ``R``)."""
    return name.split(":")[-1] if name else ""


def _requalify(nick: str | None, name: str) -> str:
    """Build ``Nick:Name`` from a (possibly already-qualified) source ``name``."""
    unq = _unqual(name)
    return f"{nick}:{unq}" if nick else unq


def _quote(s: str) -> str:
    """Quote a symbol name the KiCad way (escape ``\\`` then ``"`` and newlines)."""
    body = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{body}"'


# --------------------------------------------------------------------------- #
# Source coercion
# --------------------------------------------------------------------------- #
def _coerce_sources(sources: object) -> list[model.Library]:
    """Normalize ``sources`` into a list of :class:`model.Library`.

    Accepts a single source or an iterable of sources; each item is a
    :class:`model.Library`, a ``.kicad_sym`` path, or a template ``.kicad_sch``
    path (its inline ``lib_symbols`` is harvested).
    """
    if sources is None:
        return []
    if isinstance(sources, (model.Library, str, bytes, os.PathLike)):
        items: list = [sources]
    else:
        items = list(sources)  # type: ignore[arg-type]
    return [_coerce_one(item) for item in items]


def _coerce_one(src: object) -> model.Library:
    if isinstance(src, model.Library):
        return src
    if not isinstance(src, (str, bytes, os.PathLike)):
        fail("SYMBOL_NOT_FOUND", f"unsupported symbol source: {type(src).__name__}")
    p = Path(os.fspath(src))
    if p.suffix.lower() == ".kicad_sym":
        return kicad_lib.read(p)
    root = sexpr.parse(_read_text(p))
    if root.tag == "kicad_symbol_lib":
        return kicad_lib.read(p)
    libnode = root.find("lib_symbols")
    if libnode is None:
        fail("SYMBOL_NOT_FOUND", f"no lib_symbols in template source {p}")
    return kicad_lib.library_from_lib_symbols(libnode, str(p))


def _read_text(path: os.PathLike | str) -> str:
    """Read a UTF-8 text source bounded by ``MAX_FILE_BYTES``."""
    data = Path(path).read_bytes()
    if len(data) > MAX_FILE_BYTES:
        fail("KICAD_SEXPR_TOOBIG", f"file exceeds {MAX_FILE_BYTES} bytes")
    return data.decode("utf-8")
