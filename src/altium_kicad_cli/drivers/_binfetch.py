"""Tool resolution + optional, hardened auto-download for the external converters.

MS10 shells out to two **external Apache-2.0 Rust binaries** — ``nlbn`` (LCSC -> KiCad)
and ``npnp`` (LCSC -> Altium) by ``linkyourbin``. This module finds a runnable binary
and, *only when explicitly enabled*, downloads a **version-pinned, SHA-256-verified**
prebuilt release. Nothing here imports, vendors, links, or copies source from those
projects — they remain separate processes invoked via :func:`..safety.run_subprocess`.

Resolution order (see SPEC MS10 §1.1)::

    1. PATH            -> shutil.which(tool)
    2. cache dir       -> a previously downloaded + verified binary
    3. auto-download   -> pinned GitHub release, ONLY when opted-in
    4. otherwise None  -> the caller prints install_hint(tool)

Auto-download is **off by default** (``--auto-download`` / ``AKCLI_BINFETCH_AUTO=1`` /
config). When on it is ``https``-only, streamed under a size cap, SHA-256-verified
*before* extraction, path-traversal-guarded, and atomically installed. A positively
detected integrity failure raises :class:`..errors.AkcliError`
(``BINFETCH_CHECKSUM`` / ``BINFETCH_DOWNLOAD``); a *merely absent* tool never raises —
:func:`resolve` returns ``None``.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from ..errors import AkcliError, fail

__all__ = ["resolve", "install_hint", "NLBN_TAG", "NPNP_TAG"]

# --------------------------------------------------------------------------- #
# Pinned release tables (baked in; pin by TAG, never "latest").
#   key: (os, arch) -> (asset_name, sha256_hex_or_None)
# nlbn checksums came from the release API ``assets[].digest`` for v1.0.31.
# --------------------------------------------------------------------------- #
NLBN_TAG = "v1.0.31"
NLBN_RELEASES: dict[tuple[str, str], tuple[str, str | None]] = {
    ("linux", "x86_64"): (
        "nlbn-linux-x86_64.tar.gz",
        "b5af4113d95dcd21941c301be17c8ee9003e3896a4e8b9a3ddf736eec8f22de5",
    ),
    ("linux", "x86_64-musl"): (
        "nlbn-linux-x86_64-musl.tar.gz",
        "77f40ad81ef14e55f407e4137e937fc6534cf82c0da7c260a0d5b2eda72ad77f",
    ),
    ("macos", "aarch64"): (
        "nlbn-macos-aarch64.tar.gz",
        "417bc82f2ef9b13b97e7670fd479300aaca96284441740918bf545e8f3089a60",
    ),
    ("macos", "x86_64"): (
        "nlbn-macos-x86_64.tar.gz",
        "98c30621e26f610cbe90563e6f9961a09deef012f15a36d0303111bf94de450d",
    ),
    ("windows", "x86_64"): (
        "nlbn-windows-x86_64.exe.zip",
        "887ddb957adc7fc4b293f5a2ee794e7a144d8d7f81299d3f3ad734f9e13474c7",
    ),
}
NLBN_URL = "https://github.com/linkyourbin/nlbn/releases/download/{tag}/{asset}"

# npnp ships a WINDOWS-x86_64 binary ONLY. No macOS/Linux prebuilt asset exists,
# and upstream publishes NO checksum -> the sha is a self-pinned TOFU placeholder.
# While it is None, auto-download of npnp is BLOCKED (we never run an unverified exe).
NPNP_TAG = "v1.0.2"
NPNP_RELEASES: dict[tuple[str, str], tuple[str, str | None]] = {
    ("windows", "x86_64"): ("npnp-v1.0.2-windows-x86_64.zip", None),
}
NPNP_URL = "https://github.com/linkyourbin/npnp/releases/download/{tag}/{asset}"

_TOOLS = ("nlbn", "npnp")

# Transport / safety constants.
_DOWNLOAD_TIMEOUT = 120.0
_MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024  # assets are ~3-4 MB; cap well above
_UA = "altium-kicad-cli (+https://github.com/tipoLi5890/altium-kicad-cli; binfetch)"


# --------------------------------------------------------------------------- #
# tool metadata accessors (read module globals at call time -> monkeypatchable)
# --------------------------------------------------------------------------- #
def _tag(tool: str) -> str:
    return {"nlbn": NLBN_TAG, "npnp": NPNP_TAG}[tool]


def _releases(tool: str) -> dict[tuple[str, str], tuple[str, str | None]]:
    return {"nlbn": NLBN_RELEASES, "npnp": NPNP_RELEASES}[tool]


def _url_template(tool: str) -> str:
    return {"nlbn": NLBN_URL, "npnp": NPNP_URL}[tool]


# --------------------------------------------------------------------------- #
# platform / arch mapping (mind the token quirks: macos=aarch64 not arm64;
# x86_64 not amd64)
# --------------------------------------------------------------------------- #
def _platform_key() -> tuple[str | None, str | None]:
    sysname = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(
        platform.system()
    )
    mach = platform.machine().lower()
    arch = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(mach)
    return sysname, arch


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _exe_name(tool: str) -> str:
    return f"{tool}.exe" if _is_windows() else tool


def _release_for(tool: str) -> tuple[str, str | None] | None:
    """Return ``(asset, sha256|None)`` for the current platform, or ``None``.

    ``None`` means "no prebuilt exists for this os/arch" -> the caller falls
    through to an install hint; it never crashes.
    """
    sysname, arch = _platform_key()
    if sysname is None or arch is None:
        return None
    return _releases(tool).get((sysname, arch))


# --------------------------------------------------------------------------- #
# cache dir (stdlib-only; no platformdirs dependency)
# --------------------------------------------------------------------------- #
def _default_cache_base() -> Path:
    sysname = platform.system()
    if sysname == "Darwin":
        return Path.home() / "Library" / "Caches" / "altium-kicad-cli"
    if sysname == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "altium-kicad-cli" / "cache"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "altium-kicad-cli"


def _cache_base(cache_dir: str | os.PathLike | None) -> Path:
    if cache_dir:
        return Path(cache_dir)
    env = os.environ.get("AKCLI_CACHE_DIR")
    if env:
        return Path(env)
    return _default_cache_base()


def _bin_root(cache_dir: str | os.PathLike | None) -> Path:
    return _cache_base(cache_dir) / "bin"


def _tool_cache_path(tool: str, cache_dir: str | os.PathLike | None) -> Path:
    return _bin_root(cache_dir) / f"{tool}-{_tag(tool)}" / _exe_name(tool)


# --------------------------------------------------------------------------- #
# opt-in gating
# --------------------------------------------------------------------------- #
def _auto_enabled(auto: bool | None) -> bool:
    if auto is not None:
        return bool(auto)
    return os.environ.get("AKCLI_BINFETCH_AUTO", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def resolve(
    tool: str,
    *,
    auto: bool | None = None,
    opener=None,
    cache_dir: str | os.PathLike | None = None,
) -> Path | None:
    """Return an absolute :class:`~pathlib.Path` to a runnable ``tool``, or ``None``.

    Order: PATH (``shutil.which``) -> cache dir -> (if ``auto``) download + verify +
    extract. Never raises for "tool simply absent"; returns ``None``. Raises
    :class:`..errors.AkcliError` only on a positively-detected integrity failure
    during an *enabled* download (``BINFETCH_CHECKSUM`` / ``BINFETCH_DOWNLOAD``).
    """
    tool = str(tool).lower()
    if tool not in _TOOLS:
        return None

    # 1. PATH
    found = shutil.which(tool)
    if found:
        return Path(found)

    # 2. cache dir
    cached = _tool_cache_path(tool, cache_dir)
    if cached.is_file():
        return cached

    # 3. opt-in auto-download
    if not _auto_enabled(auto):
        return None
    rel = _release_for(tool)
    if rel is None:
        # No prebuilt for this os/arch -> auto-download cannot help; hint instead.
        return None
    asset, sha = rel
    return _download_install(tool, asset, sha, opener=opener, cache_dir=cache_dir)


def install_hint(tool: str) -> str:
    """One-line, copy-pasteable manual-install instruction for the current platform."""
    tool = str(tool).lower()
    if tool == "nlbn":
        return (
            "install nlbn: `cargo install nlbn` or download "
            f"{NLBN_TAG} from https://github.com/linkyourbin/nlbn/releases "
            "(then put it on PATH), or re-run with --auto-download"
        )
    if tool == "npnp":
        if _is_windows():
            return (
                "install npnp: download npnp-v1.0.2-windows-x86_64.zip from "
                "https://github.com/linkyourbin/npnp/releases and put npnp.exe on "
                "PATH, or re-run with --auto-download"
            )
        return (
            "npnp ships Windows-only binaries; on macOS/Linux build it: "
            "`cargo install --git https://github.com/linkyourbin/npnp` "
            "(then put `npnp` on PATH)"
        )
    return f"install {tool} and put it on PATH"


# --------------------------------------------------------------------------- #
# download + verify + extract + atomic install (only reached when auto enabled)
# --------------------------------------------------------------------------- #
def _default_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener()


def _download_install(
    tool: str,
    asset: str,
    sha: str | None,
    *,
    opener,
    cache_dir: str | os.PathLike | None,
) -> Path:
    url = _url_template(tool).format(tag=_tag(tool), asset=asset)
    if not url.lower().startswith("https://"):
        fail("BINFETCH_DOWNLOAD", f"refusing non-https download URL: {url}")

    # npnp publishes no checksum -> refuse to run an unverified executable.
    if not sha:
        fail(
            "BINFETCH_CHECKSUM",
            f"no pinned SHA-256 for {tool} {asset}; auto-download refused. "
            + install_hint(tool),
        )

    if opener is None:
        opener = _default_opener()

    bin_root = _bin_root(cache_dir)
    bin_root.mkdir(parents=True, exist_ok=True)

    fd, tmp_archive = tempfile.mkstemp(dir=bin_root, prefix=f".{tool}-dl-", suffix=".part")
    os.close(fd)
    tmp_archive_p = Path(tmp_archive)
    tmp_extract = Path(tempfile.mkdtemp(dir=bin_root, prefix=f".{tool}-ex-"))
    try:
        digest = _stream_download(url, opener, tmp_archive_p)
        if digest.lower() != sha.lower():
            fail(
                "BINFETCH_CHECKSUM",
                f"SHA-256 mismatch for {asset}: expected {sha}, got {digest}",
            )
        _extract(tmp_archive_p, asset, tmp_extract)
        exe_src = _find_exe(tmp_extract, tool)
        if exe_src is None:
            fail("BINFETCH_DOWNLOAD", f"no {tool} executable found inside {asset}")

        if not _is_windows():
            try:
                os.chmod(exe_src, 0o755)
            except OSError:  # pragma: no cover - best-effort
                pass

        dest_dir = bin_root / f"{tool}-{_tag(tool)}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / _exe_name(tool)
        os.replace(exe_src, dest)
        return dest
    finally:
        try:
            tmp_archive_p.unlink()
        except OSError:
            pass
        shutil.rmtree(tmp_extract, ignore_errors=True)


def _stream_download(url: str, opener, dest: Path) -> str:
    """Stream ``url`` to ``dest`` under a size cap; return the SHA-256 hex digest."""
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/octet-stream"}
    )
    try:
        resp = opener.open(req, timeout=_DOWNLOAD_TIMEOUT)
    except urllib.error.HTTPError as e:  # subclass of URLError -> first
        fail("BINFETCH_DOWNLOAD", f"HTTP {getattr(e, 'code', '?')} fetching {url}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        fail("BINFETCH_DOWNLOAD", f"could not fetch {url}: {e}")

    h = hashlib.sha256()
    total = 0
    try:
        with open(dest, "wb") as fh:
            while True:
                try:
                    chunk = resp.read(65536)
                except (OSError, urllib.error.URLError) as e:
                    fail("BINFETCH_DOWNLOAD", f"read failed for {url}: {e}")
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_DOWNLOAD_BYTES:
                    fail("BINFETCH_DOWNLOAD", f"download exceeded size cap for {url}")
                h.update(chunk)
                fh.write(chunk)
    finally:
        close = getattr(resp, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # pragma: no cover - defensive
                pass
    return h.hexdigest()


def _check_member(name: str, root: Path) -> None:
    """Reject an archive member whose resolved path escapes ``root``."""
    if name.startswith("/") or name.startswith("\\"):
        fail("BINFETCH_DOWNLOAD", f"unsafe absolute archive member: {name!r}")
    if ".." in Path(name.replace("\\", "/")).parts:
        fail("BINFETCH_DOWNLOAD", f"path traversal in archive member: {name!r}")
    dest = (root / name).resolve()
    root_r = root.resolve()
    if dest != root_r and not str(dest).startswith(str(root_r) + os.sep):
        fail("BINFETCH_DOWNLOAD", f"path traversal in archive member: {name!r}")


def _extract(archive: Path, asset: str, extract_dir: Path) -> None:
    extract_dir = Path(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    if asset.endswith((".tar.gz", ".tgz")):
        import tarfile

        with tarfile.open(archive, "r:gz") as tf:
            for m in tf.getmembers():
                _check_member(m.name, extract_dir)
                if m.issym() or m.islnk():
                    fail(
                        "BINFETCH_DOWNLOAD",
                        f"refusing link member in archive: {m.name!r}",
                    )
            tf.extractall(extract_dir)
    elif asset.endswith(".zip"):
        import zipfile

        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                _check_member(name, extract_dir)
            zf.extractall(extract_dir)
    else:
        fail("BINFETCH_DOWNLOAD", f"unsupported archive type: {asset}")


def _find_exe(root: Path, tool: str) -> Path | None:
    """Locate the extracted ``tool`` binary inside ``root`` (recursively)."""
    exact = {tool, f"{tool}.exe"}
    fallback: list[Path] = []
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file():
            continue
        if p.name in exact:
            return p
        if p.name.lower().startswith(tool.lower()):
            fallback.append(p)
    return fallback[0] if fallback else None


# Re-export AkcliError so callers can ``except _binfetch.AkcliError`` if convenient.
__all__.append("AkcliError")
