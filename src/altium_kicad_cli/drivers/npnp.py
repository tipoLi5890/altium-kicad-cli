"""``npnp`` subprocess wrapper — LCSC/EasyEDA -> Altium .SchLib/.PcbLib (SPEC MS10 §2.3).

``npnp`` (Normalize Pin Net Pad) is an **external Apache-2.0 Rust binary** by
``linkyourbin`` and ships **Windows-x86_64 only** — on macOS/Linux it typically can't
be resolved (so :func:`available` returns ``False`` unless the user ``cargo install``ed
it). We never import, vendor, or modify it — we shell out via
:func:`..safety.run_subprocess` only, and **never raise when the binary is absent**.

A full single-component Altium library pair is produced by two subcommand calls:
``export-schlib`` then ``export-pcblib`` (``export-pcblib`` auto-embeds STEP when
upstream STEP exists, so ``with_3d`` needs no separate flag).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..errors import AkcliError
from ..safety import run_subprocess
from . import _binfetch
from ._convert import ConvertResult, classify, decode, norm_lcsc

__all__ = ["available", "version", "convert", "EXE"]

EXE = "npnp"
_TIMEOUT = 180.0
_VERSION_TIMEOUT = 30.0
_TARGET = "altium"


def _resolve(auto: bool | None):
    return _binfetch.resolve(EXE, auto=auto)


def available(*, auto: bool | None = None) -> bool:
    """``True`` when an ``npnp`` binary can be resolved (typically Windows-only)."""
    return _resolve(auto) is not None


def version(*, auto: bool | None = None) -> str | None:
    """Return ``npnp``'s version string, or ``None``.

    ``npnp`` has no ``version`` verb; ``--prompt`` exits 0 and may print a dotted-int.
    Parse it when present; otherwise presence is enough and we return ``None``. Never
    raises for an absent tool.
    """
    exe = _resolve(auto)
    if exe is None:
        return None
    try:
        proc = run_subprocess([str(exe), "--prompt"], timeout=_VERSION_TIMEOUT)
    except AkcliError:
        return None
    text = decode(proc.stdout) + "\n" + decode(proc.stderr)
    m = re.search(r"(\d+(?:\.\d+)+)", text)
    return m.group(1) if m else None


def _scan_artifacts(out: Path) -> list[str]:
    """Collect Altium artifacts newly present in ``out`` (.SchLib / .PcbLib)."""
    arts: list[Path] = []
    arts += sorted(out.glob("*.SchLib"))
    arts += sorted(out.glob("*.PcbLib"))
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
    """Fetch + convert one LCSC part into an Altium .SchLib/.PcbLib under ``out_dir``.

    Runs ``export-schlib`` then ``export-pcblib`` (STEP is auto-embedded into the
    .PcbLib when upstream STEP exists; npnp gives no per-export "no-3D" knob).
    Returns a :class:`ConvertResult`; **never raises** for an absent binary.
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

    schlib_argv: list[str] = [
        str(exe), "export-schlib", display, "--index", "1", "--output", str(out)
    ]
    if lcsc_english:
        schlib_argv.append("--lcsc-english")
    if force:
        schlib_argv.append("--force")

    pcblib_argv: list[str] = [
        str(exe), "export-pcblib", display, "--index", "1", "--output", str(out)
    ]
    if force:
        pcblib_argv.append("--force")

    rc = 0
    stderr_parts: list[str] = []
    for argv in (schlib_argv, pcblib_argv):
        try:
            proc = run_subprocess(argv, timeout=timeout)
        except AkcliError as e:  # KICAD_CLI_TIMEOUT / KICAD_CLI_MISSING
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
        s = decode(proc.stderr)
        if s:
            stderr_parts.append(s)
        if proc.returncode != 0:
            rc = proc.returncode
            break  # stop on the first failing subcommand

    stderr = "\n".join(stderr_parts)
    artifacts = _scan_artifacts(out)
    ok, error_code = classify(rc, stderr, artifacts)
    return ConvertResult(
        ok=ok,
        tool=EXE,
        target=_TARGET,
        lcsc_id=display,
        out_dir=str(out),
        artifacts=artifacts,
        with_3d=with_3d,
        exit_code=rc,
        available=True,
        stderr=stderr,
        error_code=error_code,
    )
