"""Low-level OLE2 / CFBF (Compound File Binary Format) byte assembler.

Self-contained, pure-stdlib (``struct``/``math`` only). Packs a ``{path: bytes}``
stream dict into a *valid* CFBF container -- the on-disk format of Altium
``.SchDoc`` / ``.SchLib`` / ``.PcbDoc`` files.

Capabilities (all needed by the fixture corpus):

* **path-qualified storages** (``"Storage1/Data"``) so multi-``Data`` SchLib and
  multi-``Header``/``Data`` PcbDoc containers can be modelled without bare-name
  collisions;
* a ``layout`` flag to *force / validate* the **miniFAT** path (every stream
  ``< 4096`` bytes) versus a multi-sector **FAT-chain** path (a stream ``>= 4096``
  bytes spanning ``>= 9`` sectors), so both reader code paths get coverage;
* byte-patch helpers (``malformed_*``) that turn a valid container into the
  hostile corpus: FAT cycle, out-of-bounds sector, bogus ``sector_shift``, huge
  ``ndifat``, truncated header, zero-length stream, missing root storage.

This module has **no dependency on any reader module**; the verifying reader used
by the self-tests lives in the sibling ``ole_writer.py`` (same fixture-generator
group). Run ``python3 cfbf_builder.py`` for an end-to-end write+re-read self-test.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# CFBF constants
# ---------------------------------------------------------------------------
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC
NOSTREAM = 0xFFFFFFFF

OLE_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
SECTOR_SIZE = 512            # v3 container (sector shift = 9)
SECTOR_SHIFT = 9
MINI_SECTOR_SIZE = 64        # mini sector shift = 6
MINI_SECTOR_SHIFT = 6
MINI_CUTOFF = 4096           # streams strictly < this go in the mini stream
ENTRIES_PER_FAT_SECTOR = SECTOR_SIZE // 4   # 128
DIR_ENTRY_SIZE = 128
DIFAT_HEADER_SLOTS = 109
FATCHAIN_MIN_SECTORS = 9     # ">= 9 sectors" requirement for the fat-chain fixture


# ---------------------------------------------------------------------------
# Directory-tree model
# ---------------------------------------------------------------------------
@dataclass
class _Entry:
    name: str
    etype: int                       # 1 storage, 2 stream, 5 root storage
    content: bytes = b""
    children: list = field(default_factory=list)   # list[_Entry]
    # filled in during layout:
    index: int = -1
    left: int = NOSTREAM
    right: int = NOSTREAM
    child: int = NOSTREAM
    start: int = ENDOFCHAIN
    size: int = 0
    color: int = 1                   # 1 = black (a balanced BST: full Child/Left/Right walk visits all)


def _cfbf_key(name: str):
    """CFBF sibling ordering: first by UTF-16 code-unit length, then upper-cased."""
    return (len(name), name.upper())


def _build_tree(streams: dict[str, bytes]) -> _Entry:
    """Turn a ``{path: bytes}`` dict into a Root Entry with a storage/stream tree."""
    root = _Entry("Root Entry", 5)
    storages: dict[str, _Entry] = {"": root}

    def get_storage(parts):
        cur = ""
        node = root
        for part in parts:
            key = f"{cur}/{part}" if cur else part
            if key not in storages:
                st = _Entry(part, 1)
                node.children.append(st)
                storages[key] = st
            node = storages[key]
            cur = key
        return node

    for path, data in streams.items():
        parts = [p for p in path.split("/") if p]
        if not parts:
            raise ValueError("empty stream path")
        parent = get_storage(parts[:-1])
        parent.children.append(_Entry(parts[-1], 2, content=bytes(data)))
    return root


def _flatten(root: _Entry) -> list:
    """Assign stable pre-order indices (Root Entry = index 0)."""
    order: list = []

    def walk(node):
        node.index = len(order)
        order.append(node)
        for c in node.children:
            walk(c)

    walk(root)
    return order


def _link_siblings(parent: _Entry):
    """Build a balanced BST over each storage's children (Child/Left/Right)."""
    kids = sorted(parent.children, key=lambda e: _cfbf_key(e.name))

    def build(lo, hi):
        if lo > hi:
            return NOSTREAM
        mid = (lo + hi) // 2
        node = kids[mid]
        node.left = build(lo, mid - 1)
        node.right = build(mid + 1, hi)
        return node.index

    parent.child = build(0, len(kids) - 1)
    for k in parent.children:
        _link_siblings(k)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def _dir_entry_bytes(e: _Entry) -> bytes:
    b = bytearray(DIR_ENTRY_SIZE)
    nm = e.name.encode("utf-16-le")[:62]          # max 31 UTF-16 units + NUL
    b[0:len(nm)] = nm
    struct.pack_into("<H", b, 64, len(nm) + 2)    # name length incl. 2-byte NUL
    b[66] = e.etype
    b[67] = e.color
    struct.pack_into("<I", b, 68, e.left)
    struct.pack_into("<I", b, 72, e.right)
    struct.pack_into("<I", b, 76, e.child)
    # 80..96 CLSID (zero); 96 state bits (zero); 100/108 timestamps (zero)
    struct.pack_into("<I", b, 116, e.start)
    struct.pack_into("<Q", b, 120, e.size)
    return bytes(b)


def _dir_bytes(order: list) -> bytes:
    out = bytearray()
    for e in order:
        out += _dir_entry_bytes(e)
    while len(out) % SECTOR_SIZE != 0:            # pad final sector with unused (nlen=0) entries
        out += b"\x00" * DIR_ENTRY_SIZE
    return bytes(out)


# ---------------------------------------------------------------------------
# Container builder
# ---------------------------------------------------------------------------
def build_cfbf(streams: dict[str, bytes], *, layout: str = "auto"):
    """Pack ``{path: bytes}`` into a CFBF container.

    ``layout``: ``"auto"`` follows the size rule (``<4096`` -> mini, else FAT);
    ``"minifat"`` asserts every stream is mini-resident; ``"fatchain"`` asserts a
    stream spans a ``>= 9``-sector FAT chain.  Returns ``(data: bytes, meta: dict)``;
    ``meta`` carries byte offsets used by the ``malformed_*`` patchers.
    """
    if layout not in ("auto", "minifat", "fatchain"):
        raise ValueError(f"unknown layout {layout!r}")

    root = _build_tree(streams)
    order = _flatten(root)
    _link_siblings(root)

    # --- classify streams: mini-resident vs regular-FAT ---------------------
    mini_entries, big_entries = [], []
    for e in order:
        if e.etype != 2:
            continue
        n = len(e.content)
        if n == 0:
            e.start, e.size = ENDOFCHAIN, 0
        elif n < MINI_CUTOFF:
            mini_entries.append(e)
        else:
            big_entries.append(e)

    if layout == "minifat" and big_entries:
        raise ValueError("layout='minifat' but a stream >= 4096 bytes is present")

    # --- pack the mini stream + miniFAT -------------------------------------
    mini_data = bytearray()
    mini_fat: list = []
    for e in mini_entries:
        nms = math.ceil(len(e.content) / MINI_SECTOR_SIZE)
        e.start = len(mini_fat)
        e.size = len(e.content)
        chunk = e.content + b"\x00" * (nms * MINI_SECTOR_SIZE - len(e.content))
        mini_data += chunk
        for j in range(nms):
            mini_fat.append(ENDOFCHAIN if j == nms - 1 else e.start + j + 1)
    num_mini_sectors = len(mini_fat)
    ministream_size = num_mini_sectors * MINI_SECTOR_SIZE

    # --- lay out the regular FAT body ---------------------------------------
    sectors: list = []
    fat: list = []

    def add_chain(blob: bytes) -> int:
        nsec = max(1, math.ceil(len(blob) / SECTOR_SIZE))
        blob = blob + b"\x00" * (nsec * SECTOR_SIZE - len(blob))
        first = len(sectors)
        for j in range(nsec):
            sectors.append(blob[j * SECTOR_SIZE:(j + 1) * SECTOR_SIZE])
            fat.append(ENDOFCHAIN if j == nsec - 1 else first + j + 1)
        return first

    for e in big_entries:
        e.start = add_chain(e.content)
        e.size = len(e.content)

    if num_mini_sectors:
        root.start = add_chain(bytes(mini_data))
        root.size = ministream_size
    else:
        root.start, root.size = ENDOFCHAIN, 0

    if num_mini_sectors:
        minifat_bytes = b"".join(struct.pack("<I", v) for v in mini_fat)
        first_minifat = add_chain(minifat_bytes)
        n_minifat = math.ceil(len(minifat_bytes) / SECTOR_SIZE)
    else:
        first_minifat, n_minifat = ENDOFCHAIN, 0

    dir_blob = _dir_bytes(order)
    first_dir = add_chain(dir_blob)
    n_dir = len(dir_blob) // SECTOR_SIZE

    # --- size the FAT itself (fixed-point: FAT must index its own sectors) ---
    non_fat = len(sectors)
    n_fat = 1
    while True:
        need = math.ceil((non_fat + n_fat) / ENTRIES_PER_FAT_SECTOR)
        if need <= n_fat:
            break
        n_fat = need
    if n_fat > DIFAT_HEADER_SLOTS:
        raise ValueError("fixture needs DIFAT spill (>109 FAT sectors); not supported here")
    first_fat = non_fat
    for _ in range(n_fat):
        fat.append(FATSECT)
    while len(fat) % ENTRIES_PER_FAT_SECTOR != 0:
        fat.append(FREESECT)
    fat_bytes = b"".join(struct.pack("<I", v) for v in fat)
    for i in range(n_fat):
        sectors.append(fat_bytes[i * SECTOR_SIZE:(i + 1) * SECTOR_SIZE])

    if layout == "fatchain":
        max_big = max((math.ceil(len(e.content) / SECTOR_SIZE) for e in big_entries), default=0)
        if max_big < FATCHAIN_MIN_SECTORS:
            raise ValueError(
                f"layout='fatchain' needs a stream spanning >= {FATCHAIN_MIN_SECTORS} "
                f"sectors (got {max_big}); enlarge the stream")

    # --- header --------------------------------------------------------------
    header = bytearray(SECTOR_SIZE)
    header[0:8] = OLE_MAGIC
    struct.pack_into("<H", header, 24, 0x003E)            # minor version
    struct.pack_into("<H", header, 26, 0x0003)            # major version (v3)
    struct.pack_into("<H", header, 28, 0xFFFE)            # byte order (LE)
    struct.pack_into("<H", header, 30, SECTOR_SHIFT)      # 9 -> 512-byte sectors
    struct.pack_into("<H", header, 32, MINI_SECTOR_SHIFT)  # 6 -> 64-byte mini sectors
    struct.pack_into("<I", header, 40, 0)                 # # directory sectors (0 for v3)
    struct.pack_into("<I", header, 44, n_fat)
    struct.pack_into("<I", header, 48, first_dir)
    struct.pack_into("<I", header, 52, 0)                 # transaction signature
    struct.pack_into("<I", header, 56, MINI_CUTOFF)
    struct.pack_into("<I", header, 60, first_minifat)
    struct.pack_into("<I", header, 64, n_minifat)
    struct.pack_into("<I", header, 68, ENDOFCHAIN)        # first DIFAT sector (none)
    struct.pack_into("<I", header, 72, 0)                 # # DIFAT sectors
    difat = [first_fat + i for i in range(n_fat)] + [FREESECT] * (DIFAT_HEADER_SLOTS - n_fat)
    struct.pack_into("<109I", header, 76, *difat)

    data = bytes(header) + b"".join(sectors)

    def sector_byte(s):
        return (s + 1) * SECTOR_SIZE

    meta = {
        "sector_size": SECTOR_SIZE,
        "n_fat": n_fat,
        "first_fat": first_fat,
        "first_dir": first_dir,
        "n_dir": n_dir,
        "first_minifat": first_minifat,
        "n_minifat": n_minifat,
        "total_sectors": len(sectors),
        "first_big_sector": (big_entries[0].start if big_entries else None),
        "fat_sector_byte": sector_byte(first_fat),
        "dir_sector_byte": sector_byte(first_dir),
        "root_index": 0,
        "dir_entry_byte": {e.name: sector_byte(first_dir) + e.index * DIR_ENTRY_SIZE
                           for e in order},
    }
    return data, meta


# ---------------------------------------------------------------------------
# Malformed-corpus constructors (build valid, then byte-patch a single field)
# ---------------------------------------------------------------------------
def _patch_fat(buf: bytearray, meta: dict, sector: int, value: int):
    struct.pack_into("<I", buf, meta["fat_sector_byte"] + sector * 4, value)


def malformed_fat_cycle() -> bytes:
    """A multi-sector FAT chain that loops (s+1 -> s) -> infinite walk without a seen-set."""
    buf, meta = build_cfbf({"FileHeader": b"A" * 6000}, layout="fatchain")
    buf = bytearray(buf)
    s = meta["first_big_sector"]
    _patch_fat(buf, meta, s + 1, s)               # ...-> s -> s+1 -> s -> ...
    return bytes(buf)


def malformed_oob_sector() -> bytes:
    """A FAT entry pointing to a sector that is in FAT-array range but past EOF.

    The sector number stays below ``n_fat * 128`` (so a chain walk does not stop on
    the ``s < len(fat)`` guard) yet its byte offset lies beyond the file, forcing a
    hardened reader's per-sector bounds check to fire.
    """
    buf, meta = build_cfbf({"FileHeader": b"A" * 6000}, layout="fatchain")
    buf = bytearray(buf)
    oob = meta["total_sectors"] + 5            # > real sectors, < n_fat*128
    _patch_fat(buf, meta, meta["first_big_sector"], oob)
    return bytes(buf)


def malformed_bad_sector_shift() -> bytes:
    """sector_shift = 7 (128-byte sectors) -> not in the allowed {9, 12}."""
    buf, _ = build_cfbf({"FileHeader": b"hello world"}, layout="minifat")
    buf = bytearray(buf)
    struct.pack_into("<H", buf, 30, 7)
    return bytes(buf)


def malformed_huge_ndifat() -> bytes:
    """A huge DIFAT-sector count -> unbounded allocation/loop without a guard."""
    buf, _ = build_cfbf({"FileHeader": b"hello world"}, layout="minifat")
    buf = bytearray(buf)
    struct.pack_into("<I", buf, 68, 1)             # first DIFAT sector = 1 (arbitrary in-file)
    struct.pack_into("<I", buf, 72, 0x7FFFFFFF)    # # DIFAT sectors
    return bytes(buf)


def malformed_truncated_header() -> bytes:
    """Valid magic but the file is shorter than the 512-byte header."""
    return OLE_MAGIC + b"\x00" * 64


def malformed_zero_length_stream() -> bytes:
    """A valid container whose only stream ('FileHeader') has length 0."""
    data, _ = build_cfbf({"FileHeader": b""}, layout="minifat")
    return data


def malformed_missing_root() -> bytes:
    """A valid container whose Root Entry type is corrupted (5 -> 0)."""
    buf, meta = build_cfbf({"FileHeader": b"hello world"}, layout="minifat")
    buf = bytearray(buf)
    buf[meta["dir_entry_byte"]["Root Entry"] + 66] = 0x00
    return bytes(buf)


MALFORMED_OLE = {
    "fat_cycle.SchDoc": malformed_fat_cycle,
    "oob_sector.SchDoc": malformed_oob_sector,
    "bad_sector_shift.SchDoc": malformed_bad_sector_shift,
    "huge_ndifat.SchDoc": malformed_huge_ndifat,
    "truncated_header.SchDoc": malformed_truncated_header,
    "zero_length_stream.SchDoc": malformed_zero_length_stream,
    "missing_root.SchDoc": malformed_missing_root,
}


if __name__ == "__main__":   # pragma: no cover - self-test
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ole_writer import read_cfbf

    cases = {
        "minifat": ({"FileHeader": b"|RECORD=1|" * 10}, "minifat"),
        "fatchain": ({"FileHeader": b"Z" * 5000}, "fatchain"),
        "qualified": ({"Storage1/Data": b"alpha", "Storage2/Data": b"beta",
                       "FileHeader": b"top"}, "auto"),
        "boundary4095": ({"FileHeader": b"q" * 4095}, "minifat"),
    }
    for label, (streams, layout) in cases.items():
        data, _meta = build_cfbf(streams, layout=layout)
        got = read_cfbf(data)
        assert got == streams, f"{label}: round-trip mismatch\n  got {got}\n  want {streams}"
        print(f"  [{label}] {len(data)} bytes, {len(got)} stream(s) OK")

    for fname, fn in MALFORMED_OLE.items():
        blob = fn()
        assert blob[:8] == OLE_MAGIC or fname == "truncated_header.SchDoc"
        print(f"  [malformed] {fname}: {len(blob)} bytes OK")

    print("cfbf_builder self-test OK")
