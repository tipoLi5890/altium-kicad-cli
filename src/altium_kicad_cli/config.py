"""Discover, parse and validate ``altium-kicad-cli.toml`` (SPEC §3.10).

Discovery walks up from the cwd; ``-C/--config`` overrides. Paths in ``[paths]``
resolve relative to the TOML file's directory. Unknown keys are rejected with
``BAD_CONFIG`` so typos never silently disable a rule.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .errors import fail

CONFIG_FILENAME = "altium-kicad-cli.toml"

# Allowed top-level tables/keys and their allowed sub-keys.
_TOP_KEYS: frozenset[str] = frozenset({"project", "rail", "paths", "erc_waiver"})
_PROJECT_KEYS: frozenset[str] = frozenset({"mcu_designator"})
_RAIL_KEYS: frozenset[str] = frozenset({"name", "voltage", "tolerance_pct"})
_WAIVER_KEYS: frozenset[str] = frozenset({"net", "rule", "reason"})


@dataclass
class Config:
    """Parsed project configuration.

    ``rails`` and ``erc_waivers`` are lists of plain dicts; ``paths`` maps a name
    (``schematic``/``dts``/``pinout_md``/...) to an absolute path string.
    """

    mcu_designator: str | None = None
    rails: list[dict] = field(default_factory=list)
    paths: dict[str, str] = field(default_factory=dict)
    erc_waivers: list[dict] = field(default_factory=list)
    source_path: str | None = None


def find_config(start: Path | str | None = None) -> Path | None:
    """Walk up from ``start`` (default cwd) returning the first config file found."""
    here = Path(start) if start is not None else Path.cwd()
    here = here.resolve()
    if here.is_file():
        here = here.parent
    for d in [here, *here.parents]:
        candidate = d / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _reject_unknown(table: dict, allowed: frozenset[str], where: str) -> None:
    extra = set(table) - allowed
    if extra:
        fail("BAD_CONFIG", f"unknown key(s) in {where}: {', '.join(sorted(extra))}")


def load_config(path: Path | str) -> Config:
    """Parse and validate a config file; unknown keys -> ``BAD_CONFIG``."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        raise
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        fail("BAD_CONFIG", f"invalid TOML in {p}: {exc}")

    _reject_unknown(data, _TOP_KEYS, "top level")

    project = data.get("project", {})
    if not isinstance(project, dict):
        fail("BAD_CONFIG", "[project] must be a table")
    _reject_unknown(project, _PROJECT_KEYS, "[project]")

    rails: list[dict] = []
    for r in data.get("rail", []) or []:
        if not isinstance(r, dict):
            fail("BAD_CONFIG", "[[rail]] entries must be tables")
        _reject_unknown(r, _RAIL_KEYS, "[[rail]]")
        rails.append(dict(r))

    waivers: list[dict] = []
    for w in data.get("erc_waiver", []) or []:
        if not isinstance(w, dict):
            fail("BAD_CONFIG", "[[erc_waiver]] entries must be tables")
        _reject_unknown(w, _WAIVER_KEYS, "[[erc_waiver]]")
        waivers.append(dict(w))

    raw_paths = data.get("paths", {})
    if not isinstance(raw_paths, dict):
        fail("BAD_CONFIG", "[paths] must be a table")
    base = p.resolve().parent
    paths: dict[str, str] = {}
    for key, val in raw_paths.items():
        if not isinstance(val, str):
            fail("BAD_CONFIG", f"[paths].{key} must be a string")
        paths[key] = str((base / val).resolve())

    return Config(
        mcu_designator=project.get("mcu_designator"),
        rails=rails,
        paths=paths,
        erc_waivers=waivers,
        source_path=str(p.resolve()),
    )
