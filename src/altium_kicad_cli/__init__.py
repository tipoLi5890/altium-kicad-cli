"""altium-kicad-cli — read Altium .SchDoc and KiCad .kicad_sch, run checks, draw KiCad.

Zero-runtime-dependency Python package (stdlib only). This top-level module exposes
the package version and the analysis/protocol version constants used across the CLI.

Name cascade (LOCKED): PyPI dist = ``altium-kicad-cli``; import package =
``altium_kicad_cli``; CLI = ``akcli``.
"""

from __future__ import annotations

__version__ = "0.0.0"

__all__ = ["__version__"]
