"""High-level OLE2/CFBF writer + a self-contained verifying reader.

Thin convenience layer over :mod:`cfbf_builder`:

* :func:`to_ole` / :func:`write_ole` -- pack a ``{path: bytes}`` stream dict into
  a ``.SchDoc``/``.SchLib``/``.PcbDoc`` byte blob or file, honouring the
  ``layout`` flag (``minifat`` / ``fatchain`` / ``auto``);
* :func:`read_cfbf` -- a **self-contained** reader that walks the CFBF red-black
  directory tree (Child/Left/Right) and returns **path-qualified** stream names
  (``"Storage/Data"``), so multi-``Data`` containers round-trip without the
  bare-name collapse of the legacy parser.

:func:`read_cfbf` exists purely to *self-validate* the generated fixtures; the
production reader is ``src/.../readers/_cfbf.py`` (a different ownership group).
It is intentionally defensive (cycle-guarded chains, bounded mini reads) so the
self-test cannot hang, but it is **not** the hardened reader and is not used at
runtime by the package.

Run ``python3 ole_writer.py`` for a write-then-re-read self-test that prints OK.
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfbf_builder
from cfbf_builder import ENDOFCHAIN, NOSTREAM, OLE_MAGIC


def to_ole(streams: dict[str, bytes], layout: str = "auto") -> bytes:
    """Pack ``{path: bytes}`` into CFBF bytes (see :func:`cfbf_builder.build_cfbf`)."""
    data, _meta = cfbf_builder.build_cfbf(streams, layout=layout)
    return data


def write_ole(path, streams: dict[str, bytes], layout: str = "auto") -> bytes:
    """Pack ``streams`` and write the container to ``path``; return the bytes."""
    data = to_ole(streams, layout)
    with open(path, "wb") as fh:
        fh.write(data)
    return data


def _u16(b, off):
    return struct.unpack_from("<H", b, off)[0]


def _u32(b, off):
    return struct.unpack_from("<I", b, off)[0]


def read_cfbf(src) -> dict[str, bytes]:
    """Read a CFBF container into a ``{qualified_path: bytes}`` dict.

    ``src`` may be a path, ``bytes`` or ``bytearray``.  Walks the directory tree
    so names are path-qualified (e.g. ``"Storage1/Data"``).  Cycle/bounds guards
    keep the self-test from hanging on hostile inputs.
    """
    if isinstance(src, (bytes, bytearray)):
        data = bytes(src)
    else:
        with open(src, "rb") as fh:
            data = fh.read()

    if len(data) < 512 or data[:8] != OLE_MAGIC:
        raise ValueError("not an OLE2/CFBF file (bad magic or truncated header)")

    ssz = 1 << _u16(data, 30)
    msz = 1 << _u16(data, 32)
    if ssz not in (512, 4096):
        raise ValueError(f"unsupported sector size {ssz}")
    first_dir = _u32(data, 48)
    mini_cutoff = _u32(data, 56)
    first_minifat = _u32(data, 60)
    first_difat = _u32(data, 68)
    ndifat = _u32(data, 72)
    per = ssz // 4

    def off(s):
        b = (s + 1) * ssz
        if b + ssz > len(data) or b < ssz:
            raise ValueError(f"sector {s} out of bounds")
        return b

    # DIFAT -> FAT
    difat = list(struct.unpack_from("<109I", data, 76))
    sec, guard = first_difat, 0
    while sec < ENDOFCHAIN and guard < 4096:
        guard += 1
        ent = struct.unpack_from(f"<{per}I", data, off(sec))
        difat += list(ent[:-1])
        sec = ent[-1]
    fat = []
    for fs in difat:
        if fs >= ENDOFCHAIN:
            continue
        fat += list(struct.unpack_from(f"<{per}I", data, off(fs)))

    def chain(start):
        out, s, seen = [], start, set()
        while s < ENDOFCHAIN and s < len(fat):
            if s in seen:
                raise ValueError("FAT cycle")
            seen.add(s)
            out.append(s)
            s = fat[s]
        return out

    def read_chain(start, size):
        b = b"".join(data[off(s):off(s) + ssz] for s in chain(start))
        return b[:size] if size else b

    # directory entries
    dirbuf = read_chain(first_dir, 0)
    entries = []
    for i in range(0, len(dirbuf), 128):
        e = dirbuf[i:i + 128]
        if len(e) < 128:
            break
        nlen = _u16(e, 64)
        name = e[:nlen - 2].decode("utf-16-le", "replace") if nlen >= 2 else ""
        entries.append({
            "name": name, "etype": e[66],
            "left": _u32(e, 68), "right": _u32(e, 72), "child": _u32(e, 76),
            "start": _u32(e, 116), "size": struct.unpack_from("<Q", e, 120)[0],
        })

    roots = [e for e in entries if e["etype"] == 5]
    if not roots:
        raise ValueError("missing root storage")
    root = roots[0]

    ministream = read_chain(root["start"], root["size"]) if root["start"] < ENDOFCHAIN else b""

    minifat, mf, seen = [], first_minifat, set()
    while mf < ENDOFCHAIN and mf < len(fat):
        if mf in seen:
            raise ValueError("miniFAT cycle")
        seen.add(mf)
        minifat += list(struct.unpack_from(f"<{per}I", data, off(mf)))
        mf = fat[mf]

    def read_mini(start, size):
        out, s, seen2 = b"", start, set()
        while s < ENDOFCHAIN and s < len(minifat):
            if s in seen2:
                raise ValueError("mini stream cycle")
            seen2.add(s)
            out += ministream[s * msz:s * msz + msz]
            s = minifat[s]
        return out[:size]

    streams: dict[str, bytes] = {}

    def visit(idx, prefix):
        if idx == NOSTREAM or idx >= len(entries):
            return
        e = entries[idx]
        visit(e["left"], prefix)
        if e["etype"] == 1:            # storage
            visit(e["child"], prefix + e["name"] + "/")
        elif e["etype"] == 2:          # stream
            if e["size"] < mini_cutoff:
                content = read_mini(e["start"], e["size"])
            else:
                content = read_chain(e["start"], e["size"])
            streams[prefix + e["name"]] = content[:e["size"]]
        visit(e["right"], prefix)

    visit(root["child"], "")
    return streams


if __name__ == "__main__":   # pragma: no cover - self-test
    samples = {
        "minifat": ({"FileHeader": b"|RECORD=HEADER|" + b"x" * 200}, "minifat"),
        "fatchain": ({"FileHeader": b"D" * 5000}, "fatchain"),
        "multi-Data (SchLib-like)": (
            {"Storage A/Data": b"sym-a", "Storage B/Data": b"sym-b",
             "Storage C/Data": b"sym-c", "FileHeader": b"lib"}, "auto"),
        "mixed mini+fat": ({"FileHeader": b"big" * 2000, "Storage1/Data": b"tiny"}, "auto"),
    }
    for label, (streams, layout) in samples.items():
        blob = to_ole(streams, layout)
        got = read_cfbf(blob)
        assert got == streams, f"{label}: {got!r} != {streams!r}"
        print(f"  [{label}] {len(blob)} bytes -> {sorted(got)} OK")
    print("ole_writer self-test OK")
