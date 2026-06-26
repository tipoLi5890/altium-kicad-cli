"""Shared result type + helpers for the LCSC -> library converter drivers.

``drivers/nlbn.py`` (KiCad) and ``drivers/npnp.py`` (Altium) both wrap an external
Rust binary via :func:`..safety.run_subprocess` and return a :class:`ConvertResult`.
Neither tool offers a differentiated error scheme (nlbn: exit 1 = any error; npnp:
exit 2 = any error; message on stderr as ``Error: <msg>``), so failures are mapped to
the package's own ``errors.py`` codes here (SPEC MS10 §2.4).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ConvertResult:
    """Outcome of a single ``convert()`` call (one LCSC part -> a library)."""

    ok: bool                      # converter exit 0 AND >=1 artifact found
    tool: str                     # "nlbn" | "npnp"
    target: str                   # "kicad" | "altium"
    lcsc_id: str                  # "C2040" (as requested; NOT parsed from filenames)
    out_dir: str
    artifacts: list[str] = field(default_factory=list)  # absolute paths produced
    with_3d: bool = False
    exit_code: int | None = None  # subprocess returncode (None if binary absent)
    available: bool = True        # was a binary resolved at all
    stderr: str = ""              # captured, decoded, human-readable reason
    error_code: str | None = None  # mapped errors.py code on failure, else None

    def to_dict(self) -> dict:
        return asdict(self)


def norm_lcsc(value: object) -> str:
    """Normalize an LCSC id to canonical ``C<digits>`` form (best-effort)."""
    s = str(value or "").strip().upper()
    if not s:
        return ""
    digits = s[1:] if s.startswith("C") else s
    return ("C" + digits) if digits else s


def decode(raw: bytes | None) -> str:
    return (raw or b"").decode("utf-8", "replace")


# Best-effort "unknown part" detection from a converter's stderr.
_NOT_FOUND_MARKERS = (
    "no results found",
    "no result found",
    "no part",
    "not found",
    "no such",
    "unknown lcsc",
)


def _looks_not_found(stderr: str) -> bool:
    low = stderr.lower()
    return any(m in low for m in _NOT_FOUND_MARKERS)


def classify(returncode: int, stderr: str, artifacts: list[str]) -> tuple[bool, str | None]:
    """Map a finished converter run onto ``(ok, error_code)`` (SPEC MS10 §2.4).

    ``returncode == 0`` + artifacts -> success. ``0`` with nothing on disk ->
    ``CONVERT_NO_ARTIFACTS``. Non-zero -> ``CONVERT_PART_NOT_FOUND`` when stderr
    indicates an unknown LCSC id, else ``CONVERT_FAILED``.
    """
    if returncode == 0:
        if artifacts:
            return True, None
        return False, "CONVERT_NO_ARTIFACTS"
    if _looks_not_found(stderr):
        return False, "CONVERT_PART_NOT_FOUND"
    return False, "CONVERT_FAILED"
