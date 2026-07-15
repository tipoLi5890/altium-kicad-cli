"""Optional ``pdftotext`` (poppler) wrapper for datasheet quote verification.

Advisory only, mirroring the ``kicad-cli`` driver contract: every entry point
is gated on :func:`shutil.which`, a missing tool is non-fatal (``None``), and
subprocesses run through :func:`..safety.run_subprocess` (``shell=False``,
absolute exe, timeout + output cap). When the tool is absent, facts
verification downgrades quote checks to a NOTE instead of pretending they ran.
"""

from __future__ import annotations

import re
import shutil

from ..safety import run_subprocess

__all__ = ["available", "page_text", "quote_present"]

EXE = "pdftotext"


def available() -> bool:
    return shutil.which(EXE) is not None


def page_text(pdf_path: str, page: int) -> str | None:
    """Extracted text of ONE page (1-based), or ``None`` (tool absent/failed)."""
    exe = shutil.which(EXE)
    if exe is None or page < 1:
        return None
    try:
        proc = run_subprocess(
            [exe, "-f", str(page), "-l", str(page), "-layout",
             str(pdf_path), "-"],
            timeout=30,
        )
    except Exception:                     # missing/timeout: advisory → None
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout
    if isinstance(out, bytes):
        return out.decode("utf-8", errors="replace")
    return out or ""


_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def quote_present(pdf_path: str, page: int, quote: str) -> bool | None:
    """``True``/``False`` when the check RAN; ``None`` when it could not.

    Whitespace-normalized, case-insensitive substring match — datasheet PDFs
    reflow table text, so exact matching would reject genuine quotes.
    """
    text = page_text(pdf_path, page)
    if text is None:
        return None
    return _norm(quote) in _norm(text)
