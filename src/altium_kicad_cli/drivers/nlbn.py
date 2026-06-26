"""``nlbn`` subprocess wrapper — LCSC/EasyEDA -> KiCad symbol/footprint/3D (SPEC MS10 §2.2).

``nlbn`` is an **external Apache-2.0 Rust binary** by ``linkyourbin``; we never import,
vendor, or modify it — we shell out via :func:`..safety.run_subprocess` only. This
module mirrors :mod:`.kicad_cli`: module-level :data:`EXE`, :func:`available`,
:func:`version`, gated on :func:`._binfetch.resolve`, and **never raises when the binary
is absent** (it returns a structured ``ConvertResult(available=False)``).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..errors import AkcliError
from ..safety import run_subprocess
from . import _binfetch
from ._convert import ConvertResult, classify, decode, norm_lcsc

__all__ = ["available", "version", "convert", "EXE"]

EXE = "nlbn"
_TIMEOUT = 180.0          # network fetch + convert; bounded so a hang can't wedge the CLI
_VERSION_TIMEOUT = 30.0
_TARGET = "kicad"


def _resolve(auto: bool | None):
    return _binfetch.resolve(EXE, auto=auto)


def available(*, auto: bool | None = None) -> bool:
    """``True`` when an ``nlbn`` binary can be resolved (PATH / cache / auto)."""
    return _resolve(auto) is not None


def version(*, auto: bool | None = None) -> str | None:
    """Return ``nlbn``'s version string, or ``None``.

    ``nlbn`` has no dedicated ``version`` verb; bare ``nlbn`` prints version + help.
    Parse the first dotted-int run from stdout/stderr. Never raises for an absent tool.
    """
    exe = _resolve(auto)
    if exe is None:
        return None
    try:
        proc = run_subprocess([str(exe)], timeout=_VERSION_TIMEOUT)
    except AkcliError:  # tool present but unrunnable / timed out
        return None
    text = decode(proc.stdout) + "\n" + decode(proc.stderr)
    m = re.search(r"(\d+(?:\.\d+)+)", text)
    return m.group(1) if m else None


def _scan_artifacts(out: Path, lib_name: str) -> list[str]:
    """Collect KiCad artifacts newly present in ``out`` (sym / footprint / 3D)."""
    arts: list[Path] = []
    arts += sorted(out.glob("*.kicad_sym"))
    arts += sorted(out.glob("*.pretty/*.kicad_mod"))
    arts += sorted(out.glob("*.3dshapes/*.step"))
    seen: set[str] = set()
    result: list[str] = []
    for p in arts:
        ap = str(p.resolve())
        if ap not in seen:
            seen.add(ap)
            result.append(ap)
    return result


def convert(
    lcsc_id: str,
    out_dir: str | Path,
    *,
    with_3d: bool = False,
    lib_name: str = "akcli",
    force: bool = False,
    lcsc_english: bool = False,
    auto: bool | None = None,
    timeout: float = _TIMEOUT,
) -> ConvertResult:
    """Fetch + convert one LCSC part into a KiCad library under ``out_dir``.

    ``with_3d`` selects the converter scope: ``--full`` (symbol + footprint + 3D STEP)
    when ``True``, else ``--symbol --footprint`` (no 3D — nlbn has no separate 3D
    toggle). Returns a :class:`ConvertResult`; **never raises** for an absent binary.
    """
    display = norm_lcsc(lcsc_id)
    out = Path(out_dir)

    exe = _resolve(auto)
    if exe is None:
        return ConvertResult(
            ok=False,
            tool=EXE,
            target=_TARGET,
            lcsc_id=display,
            out_dir=str(out),
            artifacts=[],
            with_3d=with_3d,
            exit_code=None,
            available=False,
            stderr="",
            error_code="KICAD_CLI_MISSING",
        )

    out.mkdir(parents=True, exist_ok=True)

    argv: list[str] = [str(exe)]
    if with_3d:
        argv.append("--full")
    else:
        argv += ["--symbol", "--footprint"]
    argv += ["--lcsc-id", display, "-o", str(out), "--lib-name", lib_name]
    if force:
        argv.append("--overwrite")
    if lcsc_english:
        argv.append("--lcsc-english")

    try:
        proc = run_subprocess(argv, timeout=timeout)
    except AkcliError as e:  # KICAD_CLI_TIMEOUT / KICAD_CLI_MISSING from run_subprocess
        return ConvertResult(
            ok=False,
            tool=EXE,
            target=_TARGET,
            lcsc_id=display,
            out_dir=str(out),
            artifacts=[],
            with_3d=with_3d,
            exit_code=None,
            available=True,
            stderr=e.message,
            error_code=e.code,
        )

    stderr = decode(proc.stderr)
    artifacts = _scan_artifacts(out, lib_name)
    ok, error_code = classify(proc.returncode, stderr, artifacts)
    return ConvertResult(
        ok=ok,
        tool=EXE,
        target=_TARGET,
        lcsc_id=display,
        out_dir=str(out),
        artifacts=artifacts,
        with_3d=with_3d,
        exit_code=proc.returncode,
        available=True,
        stderr=stderr,
        error_code=error_code,
    )
