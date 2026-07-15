"""akcli — read Altium .SchDoc and KiCad .kicad_sch, run checks, draw KiCad.

Zero-runtime-dependency Python package (stdlib only). This top-level module exposes
the package version and the analysis/protocol version constants used across the CLI.

Name cascade (LOCKED): PyPI dist = ``akcli``; import package =
``akcli``; CLI = ``akcli``.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version


def _resolve_version() -> str:
    """Report the version of the code actually running, dev checkout or install.

    A co-located ``pyproject.toml`` (``project.name == "akcli"``) means we are
    executing FROM the source tree; that file is the freshest truth and WINS —
    an editable or older install otherwise pins stale metadata, so bumping the
    working tree would not move ``akcli --version`` and a real update reads as
    "unchanged" (the exact confusion the 0.7.0/design-integrity overlap caused).
    An installed wheel has no such sibling pyproject, so it falls through to the
    dist metadata. Last-resort ``"0.0.0"`` only if neither source is readable.
    """
    try:
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with pyproject.open("rb") as fh:
            project = tomllib.load(fh).get("project", {})
        if project.get("name") == "akcli" and project.get("version"):
            return project["version"]
    except Exception:
        pass
    try:
        return _pkg_version("akcli")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _resolve_version()

__all__ = ["__version__"]
