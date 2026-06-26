"""Fully-offline tests for :mod:`altium_kicad_cli.drivers._binfetch` (SPEC MS10 §1).

NO real network and NO real binaries. The three seams are exercised with fakes:

* ``shutil.which`` is monkeypatched (PATH branch).
* the cache dir is a ``tmp_path`` we pre-populate (cache branch).
* the download ``opener`` is a fake exposing ``open(req, timeout=...)`` whose response
  ``.read()`` yields bytes of a ``.tar.gz`` built on the fly with stdlib ``tarfile``
  (auto-download branch). The pinned SHA-256 is monkeypatched to the fixture's hash so
  verification passes; a mismatch and the npnp-no-checksum block are asserted to refuse.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import tarfile

import pytest

from altium_kicad_cli.drivers import _binfetch
from altium_kicad_cli.errors import EXIT, AkcliError


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)
        self.closed = False

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n if (n is not None and n >= 0) else None)

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    """Injectable HTTP transport: returns canned bytes, records every call."""

    def __init__(self, data: bytes | None = None, *, exc: BaseException | None = None) -> None:
        self._data = data
        self._exc = exc
        self.calls: list[str] = []

    def open(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        self.calls.append(url)
        if self._exc is not None:
            raise self._exc
        return _FakeResp(self._data or b"")


def _make_targz(member: str, content: bytes) -> tuple[bytes, str]:
    """Build a ``.tar.gz`` containing one ``member`` -> (bytes, sha256_hex)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(member)
        info.size = len(content)
        info.mode = 0o644
        tf.addfile(info, io.BytesIO(content))
    data = buf.getvalue()
    return data, hashlib.sha256(data).hexdigest()


def _force_platform(monkeypatch, sysname: str, machine: str) -> None:
    monkeypatch.setattr(_binfetch.platform, "system", lambda: sysname)
    monkeypatch.setattr(_binfetch.platform, "machine", lambda: machine)


# --------------------------------------------------------------------------- #
# resolution order: PATH / cache / disabled
# --------------------------------------------------------------------------- #
def test_resolve_path_first(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/nlbn")
    got = _binfetch.resolve("nlbn", cache_dir=tmp_path)
    assert got is not None
    assert str(got) == "/usr/local/bin/nlbn"


def test_resolve_cache_hit(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    exe = tmp_path / "bin" / f"nlbn-{_binfetch.NLBN_TAG}" / "nlbn"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    got = _binfetch.resolve("nlbn", cache_dir=tmp_path)
    assert got == exe


def test_resolve_disabled_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.delenv("AKCLI_BINFETCH_AUTO", raising=False)
    # auto defaults off -> we never touch the network, just return None.
    assert _binfetch.resolve("nlbn", cache_dir=tmp_path) is None


def test_resolve_unknown_tool_is_none(tmp_path):
    assert _binfetch.resolve("totally-unknown", auto=True, cache_dir=tmp_path) is None


def test_auto_enabled_via_env(monkeypatch):
    monkeypatch.setenv("AKCLI_BINFETCH_AUTO", "1")
    assert _binfetch._auto_enabled(None) is True
    monkeypatch.setenv("AKCLI_BINFETCH_AUTO", "0")
    assert _binfetch._auto_enabled(None) is False
    # explicit arg overrides env
    assert _binfetch._auto_enabled(True) is True
    monkeypatch.setenv("AKCLI_BINFETCH_AUTO", "yes")
    assert _binfetch._auto_enabled(None) is True


# --------------------------------------------------------------------------- #
# auto-download: success path (verify + extract + chmod + atomic place)
# --------------------------------------------------------------------------- #
def test_auto_download_success(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    _force_platform(monkeypatch, "Linux", "x86_64")

    content = b"#!/bin/sh\necho nlbn\n"
    data, sha = _make_targz("nlbn", content)
    monkeypatch.setattr(
        _binfetch,
        "NLBN_RELEASES",
        {("linux", "x86_64"): ("nlbn-linux-x86_64.tar.gz", sha)},
    )
    opener = FakeOpener(data)

    got = _binfetch.resolve("nlbn", auto=True, opener=opener, cache_dir=tmp_path)

    assert got is not None and got.is_file()
    assert got.name == "nlbn"
    assert got.parent.name == f"nlbn-{_binfetch.NLBN_TAG}"
    assert got.read_bytes() == content
    # executable bit set on POSIX
    if os.name == "posix":
        assert oct(got.stat().st_mode)[-3:] == "755"
    # https-only pinned URL was hit exactly once
    assert len(opener.calls) == 1
    url = opener.calls[0]
    assert url.startswith("https://")
    assert _binfetch.NLBN_TAG in url and "nlbn-linux-x86_64.tar.gz" in url
    # no temp leftovers in the bin root
    entries = sorted(p.name for p in (tmp_path / "bin").iterdir())
    assert entries == [f"nlbn-{_binfetch.NLBN_TAG}"]


def test_auto_download_checksum_mismatch_refuses(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    _force_platform(monkeypatch, "Linux", "x86_64")

    data, _real_sha = _make_targz("nlbn", b"payload")
    monkeypatch.setattr(
        _binfetch,
        "NLBN_RELEASES",
        {("linux", "x86_64"): ("nlbn-linux-x86_64.tar.gz", "00" * 32)},  # wrong
    )
    opener = FakeOpener(data)

    with pytest.raises(AkcliError) as ei:
        _binfetch.resolve("nlbn", auto=True, opener=opener, cache_dir=tmp_path)
    assert ei.value.code == "BINFETCH_CHECKSUM"
    assert ei.value.exit_code == EXIT["TOOL_MISSING"]
    # nothing installed, and the partial download was cleaned up
    dest = tmp_path / "bin" / f"nlbn-{_binfetch.NLBN_TAG}" / "nlbn"
    assert not dest.exists()
    leftovers = [p.name for p in (tmp_path / "bin").iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_npnp_no_checksum_blocks_download(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    _force_platform(monkeypatch, "Windows", "x86_64")
    # default NPNP_RELEASES has sha == None for windows/x86_64
    opener = FakeOpener(b"should-never-be-read")

    with pytest.raises(AkcliError) as ei:
        _binfetch.resolve("npnp", auto=True, opener=opener, cache_dir=tmp_path)
    assert ei.value.code == "BINFETCH_CHECKSUM"
    # refused BEFORE any network access (no exec of an unverified binary)
    assert opener.calls == []


# --------------------------------------------------------------------------- #
# platform / arch mapping + coverage gaps -> None + install hint, never crash
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "machine,expected_arch",
    [("x86_64", "x86_64"), ("amd64", "x86_64"), ("arm64", "aarch64"), ("aarch64", "aarch64")],
)
def test_platform_arch_mapping(monkeypatch, machine, expected_arch):
    _force_platform(monkeypatch, "Darwin", machine)
    sysname, arch = _binfetch._platform_key()
    assert sysname == "macos"
    assert arch == expected_arch


def test_platform_unknown_arch_is_none(monkeypatch):
    _force_platform(monkeypatch, "Linux", "riscv64")
    assert _binfetch._platform_key() == ("linux", None)


def test_nlbn_linux_aarch64_no_prebuilt(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    _force_platform(monkeypatch, "Linux", "aarch64")
    # auto requested, but no asset exists -> None (never crashes)
    assert _binfetch.resolve("nlbn", auto=True, cache_dir=tmp_path) is None
    assert _binfetch._release_for("nlbn") is None


def test_nlbn_windows_aarch64_no_prebuilt(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    _force_platform(monkeypatch, "Windows", "arm64")
    assert _binfetch.resolve("nlbn", auto=True, cache_dir=tmp_path) is None


def test_npnp_non_windows_falls_through(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    _force_platform(monkeypatch, "Linux", "x86_64")
    assert _binfetch.resolve("npnp", auto=True, cache_dir=tmp_path) is None
    assert _binfetch._release_for("npnp") is None


# --------------------------------------------------------------------------- #
# install hints
# --------------------------------------------------------------------------- #
def test_install_hint_nlbn():
    hint = _binfetch.install_hint("nlbn")
    assert "cargo install nlbn" in hint
    assert _binfetch.NLBN_TAG in hint
    assert "--auto-download" in hint


def test_install_hint_npnp_non_windows(monkeypatch):
    _force_platform(monkeypatch, "Linux", "x86_64")
    hint = _binfetch.install_hint("npnp")
    assert "Windows-only" in hint
    assert "cargo install --git" in hint


def test_install_hint_npnp_windows(monkeypatch):
    _force_platform(monkeypatch, "Windows", "x86_64")
    hint = _binfetch.install_hint("npnp")
    assert "npnp.exe" in hint
    assert "--auto-download" in hint


# --------------------------------------------------------------------------- #
# archive path-traversal guard
# --------------------------------------------------------------------------- #
def test_extract_rejects_path_traversal(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("../evil")
        payload = b"evil"
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    archive = tmp_path / "bad.tar.gz"
    archive.write_bytes(buf.getvalue())

    dest = tmp_path / "ex"
    with pytest.raises(AkcliError) as ei:
        _binfetch._extract(archive, "bad.tar.gz", dest)
    assert ei.value.code == "BINFETCH_DOWNLOAD"
    assert not (tmp_path / "evil").exists()


def test_check_member_rejects_absolute(tmp_path):
    with pytest.raises(AkcliError) as ei:
        _binfetch._check_member("/etc/passwd", tmp_path)
    assert ei.value.code == "BINFETCH_DOWNLOAD"


# --------------------------------------------------------------------------- #
# cache path layout
# --------------------------------------------------------------------------- #
def test_tool_cache_path_layout(tmp_path):
    p = _binfetch._tool_cache_path("nlbn", tmp_path)
    assert p == tmp_path / "bin" / f"nlbn-{_binfetch.NLBN_TAG}" / _binfetch._exe_name("nlbn")
