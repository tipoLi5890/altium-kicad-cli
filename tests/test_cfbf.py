"""Tests for the hardened OLE2/CFBF reader (readers/_cfbf.py).

Key requirements (SPEC §3.2):
* ``ole_minifat.SchDoc`` and ``ole_fatchain.SchDoc`` parse to IDENTICAL records;
* multi-storage containers do NOT collide under ``read_streams_qualified``;
* every ``tests/fixtures/malformed/*.SchDoc`` raises a STRUCTURED error
  (``AkcliError``) -- never a crash or hang -- within a small time budget.
"""

from __future__ import annotations

import signal
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from altium_kicad_cli.errors import ERROR_CODES, AkcliError
from altium_kicad_cli.readers import _cfbf
from altium_kicad_cli.readers.altium_records import parse_records

FIX = Path(__file__).resolve().parent / "fixtures"
GEN = FIX / "_gen"
if str(GEN) not in sys.path:
    sys.path.insert(0, str(GEN))
import ole_writer  # noqa: E402  (fixture generator, self-contained stdlib)


@contextmanager
def time_budget(seconds: int = 5):
    """Fail (rather than hang) if the body runs longer than ``seconds``.

    Uses ``signal.alarm`` where available (POSIX); a no-op on platforms without
    it (e.g. Windows), where the malformed-corpus guards are still asserted.
    """
    if not hasattr(signal, "SIGALRM"):
        yield
        return
    def _handler(signum, frame):  # pragma: no cover - only on a real hang
        raise TimeoutError("operation exceeded time budget (possible infinite loop)")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


# --- valid containers --------------------------------------------------------
def test_minifat_and_fatchain_streams_present():
    mini = _cfbf.read_streams(FIX / "ole_minifat.SchDoc")
    fat = _cfbf.read_streams(FIX / "ole_fatchain.SchDoc")
    assert "FileHeader" in mini
    assert "FileHeader" in fat
    assert len(mini["FileHeader"]) > 0
    assert len(fat["FileHeader"]) > 0


def test_minifat_and_fatchain_parse_to_identical_records():
    mini = _cfbf.read_streams(FIX / "ole_minifat.SchDoc")["FileHeader"]
    fat = _cfbf.read_streams(FIX / "ole_fatchain.SchDoc")["FileHeader"]
    # The fat-chain FileHeader is NUL-padded (different bytes / container layout)
    # but the framing strips trailing NULs -> identical records.
    assert parse_records(mini, drop_header=True) == parse_records(fat, drop_header=True)


def test_read_from_bytes_matches_read_from_path():
    raw = (FIX / "ole_minifat.SchDoc").read_bytes()
    assert _cfbf.read_streams(raw) == _cfbf.read_streams(FIX / "ole_minifat.SchDoc")


def test_net_regression_fixtures_all_parse():
    for name in ("shared_name_label", "junction_cross", "t_junction",
                 "no_erc", "two_gnd_ports"):
        streams = _cfbf.read_streams(FIX / f"{name}.SchDoc")
        recs = parse_records(streams["FileHeader"], drop_header=True)
        assert recs, f"{name}: no records parsed"


# --- path-qualified vs bare-name keying -------------------------------------
def test_qualified_streams_do_not_collide():
    blob = ole_writer.to_ole(
        {"Storage1/Data": b"alpha", "Storage2/Data": b"beta", "FileHeader": b"top"}
    )
    qual = _cfbf.read_streams_qualified(blob)
    assert qual == {"Storage1/Data": b"alpha", "Storage2/Data": b"beta",
                    "FileHeader": b"top"}
    # bare-name keying collapses the two "Data" streams into one survivor.
    bare = _cfbf.read_streams(blob)
    assert set(bare) == {"Data", "FileHeader"}
    assert len(bare) < len(qual)


def test_boundary_stream_sizes_4095_and_4096():
    # 4095 < mini_cutoff -> mini-resident; 4096 -> regular FAT chain.
    for n, layout in ((4095, "minifat"), (4096, "auto")):
        blob = ole_writer.to_ole({"FileHeader": b"q" * n}, layout=layout)
        got = _cfbf.read_streams(blob)["FileHeader"]
        assert got == b"q" * n


# --- malformed corpus: structured errors, never crash/hang ------------------
_MALFORMED_RAISES = {
    "fat_cycle.SchDoc": "ALTIUM_FAT_CYCLE",
    "oob_sector.SchDoc": "ALTIUM_OOB_SECTOR",
    "bad_sector_shift.SchDoc": "ALTIUM_BAD_SECTOR_SHIFT",
    "huge_ndifat.SchDoc": "ALTIUM_ALLOC_GUARD",
    "truncated_header.SchDoc": "ALTIUM_MALFORMED",
    "missing_root.SchDoc": "ALTIUM_MALFORMED",
}


@pytest.mark.parametrize("fname,code", sorted(_MALFORMED_RAISES.items()))
def test_malformed_ole_raises_structured_error(fname, code):
    path = FIX / "malformed" / fname
    with time_budget(5):
        with pytest.raises(AkcliError) as ei:
            _cfbf.read_streams(path)
    assert ei.value.code == code
    assert ei.value.code in ERROR_CODES


def test_zero_length_stream_is_valid_but_empty():
    # A zero-length stream is structurally valid OLE; its emptiness is handled
    # downstream (no records), not a CFBF-level error -- but must not crash/hang.
    with time_budget(5):
        streams = _cfbf.read_streams(FIX / "malformed" / "zero_length_stream.SchDoc")
    assert streams.get("FileHeader") == b""


def test_every_malformed_schdoc_is_handled_within_budget():
    # Blanket guard: every malformed .SchDoc either raises AkcliError or returns
    # cleanly -- never an unstructured crash or an infinite loop.
    for path in sorted((FIX / "malformed").glob("*.SchDoc")):
        with time_budget(5):
            try:
                _cfbf.read_streams(path)
            except AkcliError as exc:
                assert exc.code in ERROR_CODES
