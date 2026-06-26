The SPEC is written. Returning it as my final message.

# altium-kicad-cli — Hardened Implementation SPEC (v1.0, FROZEN-on-merge)

> Single source of truth for implementation agents. Resolves the original plan against 9 expert
> reviews. Every CRITICAL/HIGH fix is incorporated. Where reviewers disagreed, the decision and
> rationale are stated inline. Build each file from this document with **no further design decisions**.
>
> **Name cascade (LOCKED):** repo + PyPI dist = `altium-kicad-cli`; import package = `altium_kicad_cli`;
> CLI = `akcli` (long alias `altium-kicad-cli`); plugin name = `altium-kicad`; marketplace name = `altium-kicad`.
> Built at `../altium-kicad-cli` (sibling to `solestack`). Python ≥ 3.11, zero **runtime** deps (stdlib only,
> incl. `tomllib`). Dev/test deps allowed via an extra.

---

## 0. The single most important correction (read first)

The original plan's load-bearing premise — *"reuse the already-validated parser `schdoc_netlist.py`"* — is
**wrong at the layer that matters**, confirmed by 6 independent reviews against the real solestack board and
by `hardware/CLAUDE.md`'s own warning (*"net-label 合併 bug（曾漏報 STAT 連線）… 不可全信工具輸出"*).

What is reused (the genuinely good part of `schdoc_netlist.py`):
- The **OLE2/CFBF container reader** approach (lines 30–105), and
- the **Altium record framing + `|KEY=VALUE|` field tokenizer** (lines 109–130).

What must be **rebuilt, not reused** (the parser does NONE of these correctly):
1. **Global same-name net merge.** `build()` (lines 204–211) keeps only the *first* label per geometric
   cluster via `root_name.setdefault(...)`. On the real board this splits 48 same-named `GND` ports and drops
   the `STAT`↔`LED1_GPIO_RD` alias entirely (the documented bug). → New `netbuild.py`.
2. **Junctions (RECORD 29, 71 present) and T-junctions** (a wire endpoint on another wire's mid-span). The
   `on_seg` loop (lines 198–202) only tests pins/labels, never wire vertices or junction dots. → `netbuild.py`.
3. **No-ERC markers (RECORD 22, 29 present).** Ignored entirely; ERC would re-flag every designer-blessed point.
4. **Pin electrical type** (Altium `Electrical` 0–7). Read & discarded. ERC is dead without it.
5. **Component placement / orientation / mirror / part-id** (RECORD 1 `Location.X/Y`, `Orientation`,
   pin `OwnerPartId`). Discarded; `place_component` and verify-by-re-export have no ground truth without it.
6. **`%UTF8%` twin-field decoding & `_Frac` coordinates.** `parse_records` blanket-`latin1` mangles CJK/Ω/µ;
   integer-only coords drop the `_Frac` sub-unit → off-grid misses.
7. **Multi-storage OLE containers.** `read_ole_streams` keys streams by **bare name**, so `.SchLib`
   (41× `Data`) and `.PcbDoc` (51× `Header`/`Data`) collapse to one survivor. Needs a path-qualified
   directory-tree walk.
8. **Safety.** `chain()`/`read_mini()` have no cycle detection or bounds (infinite-loop / OOM on hostile
   input); header fields (`ssz`, `ndifat`, `mini_cutoff`) are unvalidated allocation bombs.

**Therefore the parser is referred to throughout as a *starting point with a known net-naming defect*,
never "validated."** Milestone 2 ships a regression fixture reproducing the STAT/LED1 alias and asserts the
fix before any check is built on top.

---

## 1. Final architecture overview + LOCKED normalized data model

### 1.1 Layered architecture

```
                         ┌────────────────────────── CLI / Plugin surface ──────────────────────────┐
 bin/akcli (wrapper) ─▶  cli.py ─▶ subcommands: read net component check diff pinmap plan draw export
                         skills/ + commands/ (Claude Code) call `akcli …`
                         └──────────────────────────────────────────────────────────────────────────┘
                                                     │
        ┌──────────────── format-agnostic core (the "analysis brain") ────────────────┐
        │  model.py (Schematic/Component/Pin/Net/Pcb/Library + PinType enum)           │
        │  netbuild.py  ◀─ NetPrimitives ─┐    checks/{erc,power,bom,diff,pinmap}.py    │
        │  ops.py (op-list vocab + validator)   report.py   config.py   units.py        │
        │  errors.py (ERROR codes + exit codes)  safety.py (limits, safe_path, atomic)  │
        └──────────────────────────────────────────────────────────────────────────────┘
            ▲ primitives                         ▲ primitives                    │ op-list
   ┌────────┴─────────┐               ┌──────────┴──────────┐         ┌──────────┴──────────────┐
   │ Altium readers   │               │ KiCad readers       │         │ Executors               │
   │ _cfbf, records,  │               │ sexpr, kicad,       │         │ writers/kicad (xplat)   │
   │ sch, schlib, pcb │               │ kicad_lib           │         │ drivers/altium_live (win)│
   │ (READ-ONLY)      │               │ (read + symbol defs)│         │ drivers/kicad_cli (verify)│
   └──────────────────┘               └─────────────────────┘         └─────────────────────────┘
```

**Principles (LOCKED):**
- **One normalized model.** All readers emit `Schematic`/`Pcb`/`Library`; all checks, ops, report, CLI are
  format-agnostic.
- **Readers emit `NetPrimitives` (wires, junctions, labels, power ports, pins).** A single shared
  `netbuild.py` turns primitives → `Net[]`, so Altium and KiCad share the exact same net-inference logic
  (the STAT fix is written once).
- **HW/FW raise only raw data; all derived logic is in this tool / SW.** (project rule.)
- **Altium is analysis-only, never written offline.** KiCad gets a full cross-platform writer. Altium
  write/draw only via the optional Windows live driver.
- **Canonical coordinate system:** origin **top-left, +Y down**, unit **mils**, default **50-mil grid**
  (KiCad convention). Every reader normalizes *into* this system on ingest (the Altium reader negates Y).
- **All internal KiCad-writer geometry is integer nanometres** (`1 mil = 25_400 nm`, `1 mm = 1_000_000 nm`);
  convert to string only at serialize time.
- **Every emitted JSON carries `schema_version`; the op-list and bridge carry `protocol_version`.**

### 1.2 Coordinate-unit contract (LOCKED — resolves reviewer disagreement)

Reviewers split on the Altium SCH unit (one said "~10 mil/unit empirically", another "0.1 mil"). **Decision:
1 Altium schematic integer Location unit = 10 mil = 1/100 inch**, with a companion `*_Frac` field in
1/100000 of that unit. Evidence: a standard 200-mil pin has `PinLength=20` (200/20 = 10), and the sheet
extent ~1150 units ≈ 11.5 in. The "0.1 mil" figure is the *PCB* internal unit, not schematic. This constant
lives in `units.py` as `ALTIUM_SCH_MIL_PER_UNIT = 10.0` and **MUST be unit-tested** against a known pin pitch
before any coordinate is trusted. Conversion: `mil = (intval + frac/100000.0) * 10.0`.

`units.py` is the single source of truth for ALL conversions; verify-by-re-export uses **tolerance compare**
(not exact equality) to absorb mil↔mm float drift.

### 1.3 LOCKED normalized data model (`model.py`)

All dataclasses; `from __future__ import annotations`. `PinRef = tuple[str, str]` = `(designator, pin_number)`.

```python
SCHEMA_VERSION = "1.0"          # stamped on every Schematic/Pcb/Library export

class PinType(enum.Enum):       # canonical, format-agnostic
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRI_STATE = "tri_state"
    PASSIVE = "passive"
    POWER_IN = "power_in"
    POWER_OUT = "power_out"
    OPEN_COLLECTOR = "open_collector"
    OPEN_EMITTER = "open_emitter"
    NO_CONNECT = "no_connect"
    UNSPECIFIED = "unspecified"

# Mapping tables live in model.py as the single source of truth for both readers + ERC.
ALTIUM_ELECTRICAL = {           # Altium Pin.Electrical int -> PinType
    0: PinType.INPUT, 1: PinType.BIDIRECTIONAL, 2: PinType.OUTPUT,
    3: PinType.OPEN_COLLECTOR, 4: PinType.PASSIVE, 5: PinType.TRI_STATE,
    6: PinType.OPEN_EMITTER, 7: PinType.POWER_IN,
}
KICAD_PINTYPE = {               # KiCad pin-type token -> PinType
    "input": PinType.INPUT, "output": PinType.OUTPUT, "bidirectional": PinType.BIDIRECTIONAL,
    "tri_state": PinType.TRI_STATE, "passive": PinType.PASSIVE, "free": PinType.UNSPECIFIED,
    "unspecified": PinType.UNSPECIFIED, "power_in": PinType.POWER_IN, "power_out": PinType.POWER_OUT,
    "open_collector": PinType.OPEN_COLLECTOR, "open_emitter": PinType.OPEN_EMITTER,
    "no_connect": PinType.NO_CONNECT,
}

@dataclass
class Pin:
    number: str                 # pin number/designator, e.g. "2"
    name: str | None            # pin name, e.g. "P0.25"
    x_mil: float                # canonical: mils, origin top-left, +Y down (electrical endpoint/tip)
    y_mil: float
    electrical_type: PinType = PinType.UNSPECIFIED
    owner_part_id: int = 1      # multi-unit part (Altium OwnerPartId)
    unique_id: str | None = None

@dataclass
class Component:
    designator: str             # may be synthesized "$U<idx>" if missing (never dropped)
    library_ref: str | None     # symbol name / KiCad lib_id "Device:R"
    x_mil: float
    y_mil: float
    rotation: int = 0           # {0,90,180,270}
    mirror: str = "none"        # {none,x,y}
    value: str | None = None
    footprint: str | None = None
    unique_id: str | None = None
    part_count: int = 1
    sheet: str = ""             # source sheet path (provenance)
    parameters: dict[str, str] = field(default_factory=dict)
    pins: list[Pin] = field(default_factory=list)
    undesignated: bool = False  # True when designator was synthesized

@dataclass
class Net:
    name: str                   # canonical display name
    members: list[PinRef]       # SORTED stable (designator, pin_number) keys
    aliases: list[str] = field(default_factory=list)        # other explicit names on same net
    source_names: list[str] = field(default_factory=list)   # labels/ports that contributed
    is_named: bool = True
    confidence: float = 1.0     # 0..1; lowered on ambiguous merges
    merge_reasons: list[str] = field(default_factory=list)  # explainability per merge
    @property
    def stable_id(self) -> str: # hash of sorted membership — NEVER coordinate-derived
        return "net_" + hashlib.sha1("|".join(f"{d}.{p}" for d, p in self.members).encode()).hexdigest()[:12]

@dataclass
class Schematic:
    source_path: str
    source_format: str          # "altium" | "kicad"
    components: list[Component]
    nets: list[Net]
    sheets: list[str] = field(default_factory=list)
    no_erc_points: list[tuple[float, float]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)   # passive_pin_ratio, frac_present, unnamed_net_count, ...
    schema_version: str = SCHEMA_VERSION

# --- PCB is a SEPARATE sub-model (footprints/pads/nets, NOT symbol pins) ---
@dataclass
class Footprint:
    designator: str
    footprint_name: str | None
    layer: str | None
    rotation: float = 0.0
    value: str | None = None

@dataclass
class Pcb:
    source_path: str
    source_format: str
    nets: list[str]                          # net names only (v1 scope)
    footprints: list[Footprint]
    classes: list[dict] = field(default_factory=list)
    rules: list[dict] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

# --- Library model (symbol defs WITH pin electrical types) ---
@dataclass
class SymbolDef:
    name: str
    lib_id: str | None
    pins: list[Pin]
    part_count: int = 1
    extends: str | None = None
    body_sexpr: object | None = None         # KiCad: raw symbol node for writer lib_cache

@dataclass
class Library:
    source_path: str
    source_format: str
    symbols: list[SymbolDef]
    schema_version: str = SCHEMA_VERSION
```

**`NetPrimitives`** (the reader→netbuild interface, also in `model.py`):

```python
@dataclass
class WireSeg:    a: tuple[float, float]; b: tuple[float, float]; sheet: str = ""
@dataclass
class Junction:   at: tuple[float, float]; sheet: str = ""
@dataclass
class NetLabel:   at: tuple[float, float]; text: str; scope: str = "local"; sheet: str = ""  # local|global|power|port|sheet_entry
@dataclass
class PinHandle:  ref: PinRef; at: tuple[float, float]; sheet: str = ""
@dataclass
class NetPrimitives:
    wires: list[WireSeg]; junctions: list[Junction]
    labels: list[NetLabel]; pins: list[PinHandle]
    no_erc: list[tuple[float, float]]
    power_priority: bool = False             # PrjPcb PowerPortNamesTakePriority
    emit_single_pin_nets: bool = True        # PrjPcb NetlistSinglePinNets
```

---

## 2. LOCKED op-list vocabulary + JSON-schema sketch

### 2.1 Coordinate / unit contract for ops (LOCKED)
- Origin **top-left, +Y down**, units **mils**, default **50-mil grid** (pins/wire endpoints snap to grid).
- Rotation is an **enum `{0,90,180,270}`** (never free degrees — both tools quantize). `add_text` may use any angle.
- Mirror is an **enum `{none,x,y}`**. Transform order: **rotate, then mirror**.
- Wire geometry is a **structured array of `[x,y]` vertices** (even length, orthogonal segments). CSV-in-JSON
  is banned.
- Wire/port endpoints MAY be a **pin reference string `"REF.PIN"`** (e.g. `"U3.7"`); the executor snaps it to
  the pin's computed world coordinate. Raw `[x,y]` snaps to grid.

### 2.2 Op vocabulary (LOCKED — 13 ops)

| op | purpose | KiCad writer | Altium live |
|---|---|---|---|
| `place_component` | place a symbol instance | ✅ | ✅ |
| `set_component_transform` | rotate/mirror an existing component | ✅ | ✅ |
| `set_component_parameters` | set ref/value/footprint/params | ✅ | ✅ |
| `add_wire` | draw orthogonal wire (may emit many segments) | ✅ | ✅ |
| `add_junction` | explicit junction dot | ✅ | ✅ |
| `add_no_connect` | NC flag on a pin | ✅ | ✅ |
| `add_net_label` | net label (`scope: local\|global\|hierarchical`) | ✅ | ✅ |
| `place_power_port` | power symbol (sugar: `place_gnd`, `place_vcc`) | ✅ | ✅ |
| `add_bus` | bus polyline | ✅ | ⚠️ `OP_UNSUPPORTED` v1 |
| `add_bus_entry` | bus entry (fixed 2.54 mm @ 45°) | ✅ | ⚠️ `OP_UNSUPPORTED` v1 |
| `add_text` | free text/note | ✅ | ✅ |

A per-executor **capability matrix** ships as `schemas/ops.capabilities.json`; an executor returns
`ERROR: OP_UNSUPPORTED` for any op it cannot map. `place_gnd`/`place_vcc` are documented sugar over
`place_power_port` with a preset `lib_id`.

### 2.3 op-list document shape

```json
{
  "protocol_version": 1,
  "target_format": "kicad",
  "target_file": "board.kicad_sch",
  "run_id": "uuid-or-stable-key",
  "ops": [ { "op": "place_component", "...": "..." } ]
}
```

### 2.4 Per-op result object (LOCKED)

```json
{ "op_index": 0, "op": "place_component", "status": "ok|error",
  "created_uuids": ["..."], "error_code": null, "message": "" }
```

### 2.5 `schemas/ops.schema.json` sketch (authoritative; hand-rolled validator, NOT jsonschema at runtime)

```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://altium-kicad-cli/schemas/ops.schema.json",   // OWN namespace, no altium-mcp bytes
  "title": "AkcliOpList",
  "type": "object",
  "required": ["protocol_version", "target_format", "ops"],
  "properties": {
    "protocol_version": { "const": 1 },
    "target_format": { "enum": ["kicad", "altium"] },
    "target_file": { "type": "string" },
    "run_id": { "type": "string" },
    "ops": { "type": "array", "items": { "$ref": "#/$defs/op" } }
  },
  "$defs": {
    "point": { "type": "array", "items": { "type": "number" }, "minItems": 2, "maxItems": 2 },
    "endpoint": { "oneOf": [ { "$ref": "#/$defs/point" }, { "type": "string", "pattern": "^[^.]+\\.[^.]+$" } ] },
    "rotation": { "enum": [0, 90, 180, 270] },
    "mirror": { "enum": ["none", "x", "y"] },
    "op": {
      "type": "object",
      "required": ["op"],
      "oneOf": [
        { "properties": { "op": { "const": "place_component" },
            "lib_id": { "type": "string" }, "designator": { "type": "string" },
            "x_mil": { "type": "number" }, "y_mil": { "type": "number" },
            "rotation": { "$ref": "#/$defs/rotation" }, "mirror": { "$ref": "#/$defs/mirror" },
            "value": { "type": "string" }, "footprint": { "type": "string" },
            "symbol_source": { "type": "string" } },
          "required": ["op", "lib_id", "designator", "x_mil", "y_mil"] },
        { "properties": { "op": { "const": "set_component_transform" },
            "designator": { "type": "string" },
            "rotation": { "$ref": "#/$defs/rotation" }, "mirror": { "$ref": "#/$defs/mirror" } },
          "required": ["op", "designator"] },
        { "properties": { "op": { "const": "set_component_parameters" },
            "designator": { "type": "string" }, "reference": { "type": "string" },
            "value": { "type": "string" }, "footprint": { "type": "string" },
            "parameters": { "type": "object" } },
          "required": ["op", "designator"] },
        { "properties": { "op": { "const": "add_wire" },
            "vertices": { "type": "array", "items": { "$ref": "#/$defs/endpoint" }, "minItems": 2 } },
          "required": ["op", "vertices"] },
        { "properties": { "op": { "const": "add_junction" }, "at": { "$ref": "#/$defs/point" } },
          "required": ["op", "at"] },
        { "properties": { "op": { "const": "add_no_connect" }, "pin": { "type": "string" } },
          "required": ["op", "pin"] },
        { "properties": { "op": { "const": "add_net_label" }, "name": { "type": "string" },
            "at": { "$ref": "#/$defs/point" }, "scope": { "enum": ["local", "global", "hierarchical"] },
            "orientation": { "$ref": "#/$defs/rotation" } },
          "required": ["op", "name", "at"] },
        { "properties": { "op": { "const": "place_power_port" }, "lib_id": { "type": "string" },
            "net_name": { "type": "string" }, "at": { "$ref": "#/$defs/point" },
            "rotation": { "$ref": "#/$defs/rotation" } },
          "required": ["op", "lib_id", "net_name", "at"] },
        { "properties": { "op": { "const": "add_bus" },
            "vertices": { "type": "array", "items": { "$ref": "#/$defs/point" }, "minItems": 2 } },
          "required": ["op", "vertices"] },
        { "properties": { "op": { "const": "add_bus_entry" }, "at": { "$ref": "#/$defs/point" },
            "size": { "$ref": "#/$defs/point" } }, "required": ["op", "at"] },
        { "properties": { "op": { "const": "add_text" }, "text": { "type": "string" },
            "at": { "$ref": "#/$defs/point" }, "angle": { "type": "number" } },
          "required": ["op", "text", "at"] }
      ]
    }
  }
}
```

---

## 3. COMPLETE FILE MANIFEST

> Path is relative to repo root `../altium-kicad-cli/`. "Tested by" names the test file (every module
> has a dedicated test; fixtures under `tests/fixtures/`). All readers/writers map exceptions to
> `errors.py` codes — **a raw traceback never reaches the agent** (unless `--debug`).

### 3.1 Foundation (`src/altium_kicad_cli/` core — authored & FROZEN first)

| File | Purpose | Public API (signatures) | Imports | Algorithm notes | Tested by |
|---|---|---|---|---|---|
| `model.py` | LOCKED dataclasses + `PinType` enum + Altium/KiCad type maps + `NetPrimitives` | (all of §1.3) `to_json(obj)->dict`, `Schematic.export()->dict` | stdlib `dataclasses,enum,hashlib` | `Net.stable_id` = sha1 of sorted membership; `to_json` stamps `schema_version` | `test_model.py` |
| `ops.py` | op-list vocab constants, `PROTOCOL_VERSION=1`, hand-rolled validator | `PROTOCOL_VERSION:int`; `OP_NAMES:frozenset`; `validate_oplist(doc:dict)->list[OpError]`; `load_oplist(path)->dict`; `Op` typed accessors | `errors`, `schemas/*` (read at import) | Zero-dep structural validator mirroring `ops.schema.json` (`jsonschema` only in dev); rejects free angles, odd wire arrays, unknown ops with `ERROR` codes | `test_ops.py` |
| `errors.py` | ERROR-code registry + exit-code table + `AkcliError`; top-level `as_error()` wrapper | `class AkcliError(Exception)`; `EXIT:dict[str,int]`; `ERROR_CODES:frozenset`; `def fail(code:str,msg:str)->NoReturn`; `def to_exit(exc)->int` | stdlib only | Codes: `ALTIUM_BAD_MAGIC, ALTIUM_FAT_CYCLE, ALTIUM_OOB_SECTOR, ALTIUM_BAD_SECTOR_SHIFT, ALTIUM_ALLOC_GUARD, ALTIUM_MALFORMED, KICAD_SEXPR_DEPTH, KICAD_SEXPR_UNTERMINATED, KICAD_SEXPR_TOOBIG, SYMBOL_NOT_FOUND, BAD_ANGLE, NON_ORTHOGONAL_WIRE, OFF_GRID, OVERLAP, VERIFY_FAILED, OP_UNSUPPORTED, HIERARCHICAL_UNSUPPORTED, PROTOCOL_MISMATCH, PATH_OUTSIDE_ROOT, KICAD_CLI_TIMEOUT, KICAD_CLI_MISSING, BAD_CONFIG`. Exit table: §8 | `test_errors.py` |
| `safety.py` | hard limits + safe IO helpers used everywhere | `MAX_FILE_BYTES, MAX_SECTORS, MAX_RECORDS, MAX_DIR_ENTRIES, MAX_DECODED_BYTES, MAX_SEXPR_DEPTH, MAX_ATOM_BYTES, MAX_NODES`; `safe_path(base,cand)->Path`; `run_subprocess(argv,timeout,maxout)->CompletedProcess`; `atomic_write_with_backup(path,data,backup_dir)->None` | stdlib `os,subprocess,resource,signal,pathlib,shutil` | `safe_path`: realpath both, reject escapes/symlinks, never expand env from untrusted files; `run_subprocess`: `shell=False`, abs exe, `--` before paths, timeout, output cap; `atomic_write`: snapshot→temp-in-same-dir→fsync→`os.replace` | `test_safety.py`, `test_fuzz_safety.py` |
| `units.py` | all coordinate conversions + grid + tolerance | `ALTIUM_SCH_MIL_PER_UNIT=10.0`; `MIL_PER_MM=1/0.0254`; `NM_PER_MIL=25400`; `NM_PER_MM=1_000_000`; `altium_to_mil(i,frac)->float`; `mil_to_nm(m)->int`; `nm_to_mm_str(nm)->str`; `snap_mil(m,grid=50)->float`; `approx_eq(a,b,tol_nm)->bool` | stdlib | `nm_to_mm_str` strips trailing zeros/dot (KiCad float style); integer-nm math only | `test_units.py` |
| `config.py` | discover + parse + validate `altium-kicad-cli.toml` | `find_config(start:Path)->Path\|None`; `load_config(path)->Config`; `class Config` (`mcu_designator, rails:list, paths:dict, erc_waivers:list`) | `tomllib`, `errors`, `safety` | walk-up discovery from cwd; `--config` override; paths resolve relative to toml dir; reject unknown keys → `BAD_CONFIG`; schema in §3.10 | `test_config.py` |
| `report.py` | render findings + metadata caveats; text + `--json` | `render(findings,fmt,meta)->str`; `class Finding(code,severity,message,refs)`; `Severity` enum | `model`, `errors` | Always prints metadata header: passive-pin ratio, No-ERC suppressed count, unnamed-net count, frac-coord presence — so a vacuous pass is never read as clean | `test_report.py` |
| `__main__.py` | `python -m` entry | `from .cli import main; raise SystemExit(main())` | `cli` | thin shim only | covered by `test_cli.py` |
| `cli.py` | argparse dispatch, exit codes, global flags | `def main(argv=None)->int`; subcommands `read net component check diff pinmap plan draw export` | everything | global `--version` (pkg + protocol), `-C/--config`, `-v/-vv/--quiet`, `--json`, `--no-color`, `--debug`; `draw` defaults `--dry-run`, needs `--apply` to write; stdout = data, stderr = logs | `test_cli.py` |

### 3.2 Altium readers (`src/altium_kicad_cli/readers/`)

| File | Purpose | Public API | Imports | Algorithm notes | Tested by |
|---|---|---|---|---|---|
| `_cfbf.py` | **hardened** OLE2/CFBF reader; path-qualified directory tree walk | `read_streams(path_or_bytes)->dict[str,bytes]`; `read_streams_qualified(...)->dict[str,bytes]` (e.g. `"Components6/Data"`) | `struct`, `safety`, `errors` | Port of `schdoc_netlist.read_ole_streams` lines 30–105 **with**: `len>=512` guard; assert `ssz_shift∈{9,12}`, `msz_shift==6`, `mini_cutoff==4096`; cycle-detected `chain/read_mini` (seen-set + `MAX_SECTORS` cap) → `ALTIUM_FAT_CYCLE`; range-check every `off(s)` → `ALTIUM_OOB_SECTOR`; **walk red-black dir tree (Child/Left/Right) for path-qualified, non-colliding names** (fixes 41× `Data`/51× `Header`); guard missing root-storage; DIFAT-spillover (>109) → clear `ALLOC_GUARD` error | `test_cfbf.py`, `test_fuzz_safety.py` |
| `altium_records.py` | record framing + field tokenizer + `%UTF8%` + `_Frac` + electrical map + RECORD-ID constants | `parse_records(buf,drop_header:bool)->list[dict]`; `fields(r)->dict`; `gi(d,k,default)`; `coord(d,key)->float` (assembles int+frac→mil); `RECORDS:dict` | `units`, `model`, `safety`, `errors` | Port of lines 109–130 **with**: `%UTF8%`-prefixed keys decoded UTF-8 (re-encode latin1→bytes→utf-8); `_Frac` companion assembled via `units.altium_to_mil`; `Electrical`→`PinType`; **header detection** (drop leading record only if it's the schematic HEADER, not unconditional `[1:]`) to fix SchLib/PcbDoc OwnerIndex base; record/byte caps → `MAX_RECORDS`. RECORD IDs: 1=Component,2=Pin,6=Polyline,15=SheetSymbol,16=SheetEntry,17=PowerPort,18=Port,22=NoERC,25=NetLabel,27=Wire,29=Junction,34=Designator,41=Parameter,44/45/46/48=Implementation | `test_altium_records.py` |
| `altium_sch.py` | `.SchDoc` → `Schematic` (READ-ONLY) | `read(path)->Schematic`; `read_primitives(path)->NetPrimitives` | `_cfbf`, `altium_records`, `model`, `netbuild`, `units` | Extract: RECORD 1 placement/orientation/mirror/UniqueID; RECORD 2 pins with `Electrical`, `OwnerPartId`, tip = `Location + PinLength*dir` (negate Y into canonical); RECORD 34 designators (synthesize `$U<idx>` when missing — never drop); RECORD 41 params (value/comment); RECORD 45/46 footprint; RECORD 27 wires, 29 junctions, 22 No-ERC, 25/17 labels+power ports → emit `NetPrimitives` → `netbuild.build_nets()` | `test_altium_sch.py` |
| `altium_schlib.py` | `.SchLib` → `Library` | `read(path)->Library` | `_cfbf`, `altium_records`, `model` | Use `read_streams_qualified` — each symbol in its own storage `Data` stream; per-stream OwnerIndex base (no blind `[1:]`); refuse binary records (4th length byte ≠ 0) loudly | `test_altium_schlib.py` |
| `altium_pcb.py` | `.PcbDoc` → `Pcb` (ASCII sections only, v1) | `read(path)->Pcb` | `_cfbf`, `altium_records`, `model` | Parse **only** ASCII `|KEY=VAL|` sections: `Nets6`, `Components6`, `Classes6`, `Rules6`. **Guard:** refuse to ASCII-parse a Header-declared binary section (`Pads6/Vias6/Tracks6/Arcs6/Fills6/Regions6`) — those need per-section binary struct decoders, explicitly **deferred**. No offline verify (no Altium on mac) | `test_altium_pcb.py` |

### 3.3 Net inference (`src/altium_kicad_cli/`)

| File | Purpose | Public API | Imports | Algorithm notes | Tested by |
|---|---|---|---|---|---|
| `netbuild.py` | format-agnostic net inference (the STAT fix) | `build_nets(prims:NetPrimitives)->list[Net]` | `model`, `units` | **Pipeline (LOCKED):** (1) exact-integer geometric union-find on wire segments (coords in fine-int from `_Frac`); (2) union each **junction(29)** point onto every segment it lies on; (3) **T-junction**: union every wire vertex lying on another wire's mid-span; (4) union pins/labels lying on a segment (`on_seg`, exact integer cross-product); (5) **GLOBAL same-name merge:** group all label/power-port names per component, `name→set(roots)`, union every pair sharing any name — *this stitches the two STAT clusters and aliases STAT≡LED1_GPIO_RD*; (6) naming priority: power-port > net-label > auto, honor `power_priority`; keep all names as `aliases`, emit confidence<1 + a NOTE on multi-name nets; (7) **stable synthetic ids from sorted membership**, never `N$x_y`; (8) record `merge_reasons` for explainability; (9) multi-sheet: union by Port/SheetEntry name (net labels are sheet-local, power ports global) | `test_netbuild.py` (+ STAT/alias, junction, T-junction, NoERC, two-same-name-GND fixtures) |

### 3.4 KiCad readers (`src/altium_kicad_cli/readers/`)

| File | Purpose | Public API | Imports | Algorithm notes | Tested by |
|---|---|---|---|---|---|
| `sexpr.py` | iterative, depth/size-capped S-expr tokenizer+parser (shared by readers + writer) | `parse(text:str)->SNode`; `dumps(node:SNode)->str`; `class SNode` (preserves untouched atom text + child order) | `safety`, `errors` | **Explicit-stack** (no recursion; `setrecursionlimit` banned); enforce `MAX_SEXPR_DEPTH/MAX_ATOM_BYTES/MAX_NODES`; bounded quote/escape scan; unterminated/over-deep → `KICAD_SEXPR_*`. `SNode` keeps original token text so untouched nodes reserialize byte-identical | `test_sexpr.py`, `test_fuzz_safety.py` |
| `kicad.py` | `.kicad_sch`/`.kicad_pcb` → `Schematic`/`Pcb` | `read_sch(path)->Schematic`; `read_pcb(path)->Pcb`; `read_primitives(path)->NetPrimitives` | `sexpr`, `kicad_lib`, `model`, `netbuild`, `units` | Resolve **pin electrical types from `lib_symbols` at read time** (KiCad pins on instances carry no type); parse `(wire)`,`(junction)`,`(no_connect)`,`(label/global_label/hierarchical_label)`,`(symbol …)` with `(instances)` refdes; coords mm→mil (no Y flip; KiCad already +Y down); → `NetPrimitives` → `netbuild` | `test_kicad_reader.py` |
| `kicad_lib.py` | `.kicad_sym` + inline `lib_symbols` → `Library` | `read(path)->Library`; `resolve(lib_id, sources)->SymbolDef`; `pin_offsets(sym)->list` | `sexpr`, `model` | Resolve `(extends ...)` (load base); keep `body_sexpr` for writer's lib_cache; pin offsets in symbol-local coords for world-coord computation | `test_kicad_lib.py` |

### 3.5 KiCad writer (`src/altium_kicad_cli/writers/`)

| File | Purpose | Public API | Imports | Algorithm notes | Tested by |
|---|---|---|---|---|---|
| `geometry.py` | coord/transform core (the module that makes wires hit pins) | `pin_world(sym,inst,pin)->tuple[int,int]` (nm); `transform_point(pt,rot,mirror,origin)->...`; `grid_snap_nm(pt,grid)->...`; `mil_to_nm/nm_to_mm_str` re-exports | `units`, `model` | Integer-nm; rotation 0/90/180/270 + mirror (x/y) matrices, **rotate-then-mirror**, Y-down; transform child `(property)` positions/angles too | `test_geometry.py` |
| `sexpr_writer.py` | KiCad-faithful serializer | `serialize(node:SNode)->str` | `sexpr`, `units` | 2-space indent, KiCad string quoting/escaping, float via `nm_to_mm_str`, preserve untouched-node text + child order. **Gate:** byte-identical no-op round-trip | `test_roundtrip_byte_identity.py` |
| `lib_cache.py` | `lib_symbols` cache resolution & copy | `ensure_cached(doc,lib_id,sources)->None`; `SYMBOL_NOT_FOUND` on miss | `kicad_lib`, `sexpr`, `errors`, `config` | Requalify parent → `Nick:Name`, keep child unit names unqualified (`Name_0_1`); resolve/copy `(extends)` base; **dedup by lib_id**; copy full pin electrical types (ERC needs them); symbol source = config `.kicad_sym` paths and/or template `.kicad_sch` | `test_lib_cache.py` (incl. `C_Polarized` extends fixture) |
| `instances.py` | refdes/instances/sheet-path + `#PWR` allocation | `write_instance(doc,sym,ref,path)->None`; `alloc_pwr_ref(doc)->str`; `instances_path(doc,sheet)->str` | `sexpr`, `errors` | Write BOTH `(property "Reference")` AND `(instances (project … (path … (reference …)(unit …))))`, in sync; derive project name + root-sheet uuid; flat-only v1 (sub-sheet → `HIERARCHICAL_UNSUPPORTED`); `#PWR0xx` unique alloc; **deterministic UUIDv5** = `uuid5(sheet_uuid, designator+":"+op_index)` for idempotency | `test_instances.py` |
| `connectivity.py` | pure-Python ERC-lite — **primary** post-write gate | `verify(doc)->list[Finding]`; `auto_junctions(doc)->None` | `model`, `geometry`, `errors` | Exact-coincidence of every new wire endpoint vs pin/label/junction/port; auto-insert `(junction)` at 3+ way meets; honor `(no_connect)`; duplicate-UUID + unresolved-lib_id + invalid-instances-path checks. **Runs with no KiCad installed** | `test_writer_connectivity.py` |
| `kicad.py` | op-list executor → surgical `.kicad_sch` edits | `apply(oplist:dict,path:str,apply:bool)->list[OpResult]` | all writers + `ops`,`safety`,`errors` | Per op: snap pin-ref endpoints to `pin_world`; emit per-pin `(pin "N" (uuid …))`; **atomic write w/ backup** (snapshot→temp→fsync→re-parse+connectivity verify on TEMP→`os.replace` only on pass); mtime/hash optimistic lock; reject op-list with higher major `protocol_version` → `PROTOCOL_MISMATCH`; `--dry-run` emits ops+verify, no write | `test_kicad_writer.py` |

### 3.6 Checks (`src/altium_kicad_cli/checks/`)

| File | Purpose | Public API | Imports | Algorithm notes | Tested by |
|---|---|---|---|---|---|
| `erc.py` | electrical rule checks | `run(sch:Schematic,cfg:Config)->list[Finding]` | `model`, `report`, `config` | **Net-name-based power/ground detection** (not electrical-type — real boards are 292/298 Passive): nets touching a power port or matching rail-name set = power/ground; "IC has power+ground" tests net identity. Driver-conflict/floating gated behind **type-confidence** (fraction non-Passive) and downgraded when degenerate. Honor No-ERC suppression set (geo-match within grid tol) + config `erc_waivers`. Net-alias conflicts → NOTE (e.g. `STAT==LED1_GPIO_RD`) | `test_erc.py` |
| `power.py` | rail enumeration + decoupling heuristic | `run(sch,cfg)->list[Finding]` | `model`, `config` | Enumerate rails from power ports + config `rails`; list consumers; decoupling-cap heuristic per IC power net; optional current budget if BOM annotated; rail voltage sanity vs config | `test_power.py` |
| `bom.py` | BOM hygiene | `run(sch)->list[Finding]` | `model` | Refdes parsed as `(alpha-prefix, opt-int-suffix)`; gap-detection **only within a numeric-suffixed prefix**; skip compound refs (`J_USB_C`,`X3`); dedup duplicate-designator by UniqueID/part; missing value/footprint | `test_bom.py` |
| `diff.py` | net-level v1↔v2 diff | `run(a:Schematic,b:Schematic)->DiffReport` | `model` | **Match nets by membership** (Jaccard bipartite), NOT display name; components by **UniqueID** (Altium↔Altium) then `(value,footprint,pin-count)` signature, then refdes; report name-vs-membership changes separately; document low-confidence for cross-revision | `test_diff.py` |
| `pinmap.py` | MCU pin→net + optional cross-check (GENERIC) | `run(sch,cfg,expected:dict\|None)->list[Finding]` | `model`, `config` | Generic only: emit MCU `pin→net`; cross-check against an **external expected pin→signal table** (CSV/JSON passed in). **No DTS/pinout parsing here** — that lives in `adapters/` (keeps engine reusable). Pin-name `Pn.mm` parser; schematic authoritative, expected-table advisory | `test_pinmap.py` |

### 3.7 Drivers (`src/altium_kicad_cli/drivers/`)

| File | Purpose | Public API | Imports | Algorithm notes | Tested by |
|---|---|---|---|---|---|
| `kicad_cli.py` | optional secondary verify wrapper | `available()->bool`; `version()->tuple\|None`; `erc(path)->dict\|None`; `netlist(path)->dict\|None` | `safety`, `errors` | `shutil.which`-gated; `sch erc --format json` (≥8), fall back `export netlist` (7); **never** pass `--exit-code-violations` (erc exits 0 even with violations); nonzero/crash = our write bug; absence non-fatal (connectivity.py is primary) | `test_kicad_cli.py` (skipif no `kicad-cli`) |
| `altium_live/bridge.py` | optional Windows file-based JSON bridge (offline-unit-testable) | `send(op:dict,reqdir:Path,timeout)->dict`; `ping()->dict` | `safety`, `ops`, `errors` | atomic `request.json.tmp`→rename; poll `response.json` every 200 ms; `.lock` single-flight; `altium_ping` handshake returns `{protocol_version,altium_version}`; reject `protocol_version` mismatch → `PROTOCOL_MISMATCH`; per-run unique 0700 dir, `O_NOFOLLOW`. **Offline test mocks response.json** | `test_bridge.py` |
| `altium_live/scripts/altium_api.pas` | DelphiScript half (Windows + Altium 22+) | (Altium scripting entry) | — | **Clean-room** from Altium's public scripting API + documented method; reads request.json, drives running Altium, writes response.json. **Validated only on user's Windows box** | manual (Windows) |
| `altium_live/scripts/altium_api.PrjScr` | Altium script project wrapper | — | — | pairs with `.pas` | manual (Windows) |

### 3.8 Solestack adapter (`src/altium_kicad_cli/adapters/` — optional, in-repo, imports only public model)

| File | Purpose | Public API | Imports | Algorithm notes | Tested by |
|---|---|---|---|---|---|
| `dts.py` | Zephyr DTS/overlay + pinctrl parser → expected pin→signal table | `parse_dts(path)->dict`; `to_expected_table(dts)->dict` | stdlib | Extract `&gpio0 25`, `nordic,nrf-psel`/`NRF_PSEL` node→GPIO; output the external table `pinmap.run` consumes. Generic-Zephyr, not solestack-hardcoded | `test_dts.py` |
| `pinout_md.py` | parse human `pinout.md` table (columns `網路名`/`韌體節點`) → expected table | `parse_pinout_md(path)->dict` | stdlib | Markdown table by header; advisory source (low-severity on mismatch; pinout.md is explicitly untrusted) | `test_pinout_md.py` |

### 3.9 Plugin / packaging / tooling (repo root)

| File | Purpose | Key contents | Tested by |
|---|---|---|---|
| `.claude-plugin/plugin.json` | plugin manifest (name `altium-kicad`) | §5.1 — no `version` during dev; no `skills`/`commands` arrays (default scan) | CI `claude plugin validate` |
| `.claude-plugin/marketplace.json` | self-marketplace (`source:"./"`) | §5.2 — required `owner.name`; SEO keywords duplicated | CI `claude plugin validate . --strict` |
| `bin/akcli` | self-locating zero-dep PATH wrapper | §5.3 — mode 100755 | `test -x bin/akcli` in CI; `akcli --help` smoke |
| `bin/altium-kicad-cli` | long-alias bare command | relative symlink → `akcli` | CI smoke |
| `hooks/hooks.json` | SessionStart Python-version warning | §5.4 — stderr only, exit 0 | `jq . hooks/hooks.json` in CI |
| `pyproject.toml` | PyPI dist + console_scripts | §7.4 — setuptools backend, `packages.find where=["src"]`, EDA classifier | `python -m build && twine check dist/*` |
| `tools/sync_version.py` | stamp plugin.json/marketplace.json from pyproject version | `main()`; CI fails on drift | `test_sync_version.py` |
| `tools/seo-apply.sh` | `gh repo edit` description/homepage/topics from `docs/seo.md` | runnable activation script | manual |
| `.gitattributes` | binary/text fixture rules | §6 — `tests/fixtures/** binary`, golden/`*.kicad_sch text eol=lf` | implicit (Windows CI) |
| `.github/workflows/ci.yml` | CI matrix + validators | §6.4 | self |
| `examples/altium-kicad-cli.toml.example` | tested reference config incl. `[[erc_waiver]]` for LED1/STAT | §3.10 | `test_config.py` |
| `LICENSE` | MIT (repo) | — | — |
| `THIRD_PARTY_NOTICES.md` | MIT attribution chain for altium-mcp **patterns** | credits flaco-source (2026) + coffeenmusic/Siddharth Ahuja (2025) | — |
| `SECURITY.md` | untrusted-input threat model + enforced limits | — | — |
| `CHANGELOG.md` | SemVer + protocol_version policy | — | — |
| `README.md`, `INSTALL.md` | SEO + install UX | §7 | link-check (optional) |
| `docs/seo.md` | single source of truth for all SEO assets | §7 | — |
| `docs/config-schema.md`, `docs/cli-reference.md`, `docs/op-list-authoring.md`, `docs/op-capability-matrix.md` | contracts | — | — |

### 3.10 Config schema (`altium-kicad-cli.toml`)

```toml
[project]
mcu_designator = "U3"

[[rail]]
name = "V3V3"
voltage = 3.3
tolerance_pct = 5

[paths]
schematic = "hardware/altium/insole/main.SchDoc"   # resolved relative to THIS file's dir
dts       = "firmware/boards/ebyte/e73_2g4m08s1e/..."
pinout_md = "hardware/docs/pinout.md"

[[erc_waiver]]
net    = "LED1_GPIO_RD"
rule   = "driver_conflict"
reason = "LED1 shares MCP73831 open-drain STAT (P0.25) by design; FW reads it as input"
```

`config.load_config` rejects unknown keys → `BAD_CONFIG`; discovery walks up from cwd; `-C/--config` overrides.

### 3.11 Schemas (`schemas/`)

| File | Purpose |
|---|---|
| `ops.schema.json` | §2.5 — own `$id` namespace, own ERROR enum, `protocol_version` const |
| `ops.capabilities.json` | per-op executor support matrix (KiCad writer vs Altium live) |
| `schematic.schema.json` | `Schematic` export shape + `schema_version` |
| `netlist.schema.json` | net membership + Altium net-naming rules (same-name merge, priority, single-pin gating) |

---

## 4. PARALLEL OWNERSHIP GROUPS (zero file overlap)

**FOUNDATION (Group F) — authored FIRST and FROZEN before any other group starts.** No other group may edit
these; they are the contract everyone codes against:
`model.py, ops.py, errors.py, safety.py, units.py, config.py, report.py, __main__.py`,
`schemas/{ops,ops.capabilities,schematic,netlist}.schema.json`,
`.claude-plugin/{plugin,marketplace}.json, bin/akcli, bin/altium-kicad-cli, hooks/hooks.json, pyproject.toml,
.gitattributes`, `tests/fixtures/_gen/{altium_fixture.py,ole_writer.py,cfbf_builder.py}`,
`tests/fixtures/MANIFEST.sha256`.

> Foundation includes the **fixture generators** because multiple downstream groups need synthetic fixtures;
> generating them centrally prevents drift and gives every group a stable input.

After F is frozen, these groups proceed **in parallel** (each owns disjoint files + writes its own tests):

| Group | Files (owned exclusively) | Depends on | May start after |
|---|---|---|---|
| **A — Altium readers** | `readers/_cfbf.py, readers/altium_records.py, readers/altium_sch.py, readers/altium_schlib.py, readers/altium_pcb.py` + their tests | F | F frozen |
| **N — Net inference** | `netbuild.py` + `test_netbuild.py` | F | F frozen |
| **K — KiCad readers** | `readers/sexpr.py, readers/kicad.py, readers/kicad_lib.py` + tests | F, N (uses `build_nets`) | F frozen |
| **W — KiCad writer** | `writers/{geometry,sexpr_writer,lib_cache,instances,connectivity,kicad}.py` + tests | F, K (uses `sexpr`,`kicad_lib`) | **K's `sexpr.py`+`kicad_lib.py` exist** |
| **C — Checks** | `checks/{erc,power,bom,diff,pinmap}.py` + tests | F, model populated by A/N/K | A+N (and K for KiCad inputs) ready |
| **D — Drivers** | `drivers/kicad_cli.py, drivers/altium_live/*` + tests | F (ops, errors) | F frozen |
| **ADP — Adapter** | `adapters/{dts,pinout_md}.py` + tests | F | F frozen |
| **SEO/Docs** | `README.md, INSTALL.md, SECURITY.md, THIRD_PARTY_NOTICES.md, CHANGELOG.md, LICENSE, docs/*, tools/{seo-apply.sh,sync_version.py}, .github/workflows/ci.yml, examples/*` | F (exact names) | F frozen |
| **X — CLI glue** | `cli.py` (+ `test_cli.py`) | A, N, K, W, C, D | those groups expose stable APIs |
| **S — Skill/commands** | `skills/circuit-design/SKILL.md, commands/circuit-{review,pinmap,draw,diff}.md` | X (CLI flags pinned in `docs/cli-reference.md`) | X ready |

**Dependency order (DAG):** `F → {A, N, D, ADP, SEO}`; `F → K`; `K → W`; `{A,N,K} → C`; `{A,N,K,W,C,D} → X`; `X → S`.

`sexpr.py` is owned by **K** (not F) but is the only K file W needs — W starts as soon as `sexpr.py` +
`kicad_lib.py` land, even if `kicad.py` is still in progress. No two groups ever touch the same file.

---

## 5. Exact plugin/wrapper/hook contents

### 5.1 `.claude-plugin/plugin.json`
```json
{
  "name": "altium-kicad",
  "displayName": "Altium + KiCad EDA toolkit (read .SchDoc/.kicad_sch, ERC, draw KiCad)",
  "description": "Read Altium binary .SchDoc/.SchLib/.PcbDoc and KiCad .kicad_sch with no Altium or KiCad install, run ERC/power/pinmap/BOM/diff checks, and draw KiCad schematics. Zero-dependency Python CLI for AI coding agents. Not an Altium-to-KiCad converter.",
  "keywords": ["altium","kicad","schdoc","kicad-sch","eda","schematic","pcb","netlist","erc","claude-code","ai-agents"],
  "repository": "https://github.com/tipoLi5890/altium-kicad-cli",
  "homepage": "https://github.com/tipoLi5890/altium-kicad-cli",
  "license": "MIT"
}
```
> No `version` during active development (commit-SHA versioning). No `skills`/`commands` keys → default
> `skills/` + `commands/` scans run. The plugin root MUST equal the repo root (`source:"./"`) because `src/`,
> `bin/`, `skills/`, `commands/`, `hooks/` are all copied into the cache together.

### 5.2 `.claude-plugin/marketplace.json`
```json
{
  "name": "altium-kicad",
  "owner": { "name": "Li, ching yu" },
  "plugins": [
    {
      "name": "altium-kicad",
      "source": "./",
      "description": "Dual-format EDA toolkit + Claude Code plugin: read Altium binary .SchDoc and KiCad .kicad_sch with no EDA install, run ERC/design checks, draw KiCad. Built for AI coding agents.",
      "keywords": ["altium","kicad","schdoc","kicad-sch","eda","schematic","pcb","netlist","erc","claude-code","ai-agents"]
    }
  ]
}
```
> Required `owner.name`. **No partial `skills`/`commands` arrays** (a typo would silently drop the default
> scan). The `@`-token users type after install is the marketplace **name** (`altium-kicad`), not the repo.

### 5.3 `bin/akcli` (mode 100755)
```bash
#!/usr/bin/env bash
set -euo pipefail
# Self-locating: $CLAUDE_PLUGIN_ROOT is NOT guaranteed for bin/ executables, so derive from $0.
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
# Discover a Python >=3.11 (macOS default python3 is often 3.9; we need stdlib tomllib).
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || { echo "akcli requires Python >=3.11 (none found). Install python@3.11+ or: pipx install altium-kicad-cli" >&2; exit 1; }
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m altium_kicad_cli "$@"
```
`bin/altium-kicad-cli` = relative symlink → `akcli` (preserved in plugin cache).

### 5.4 `hooks/hooks.json`
```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 -c \"import sys; sys.stderr.write('warn: altium-kicad needs Python>=3.11; akcli auto-selects a newer interpreter if present\\n') if sys.version_info < (3,11) else None\"; exit 0"
          }
        ]
      }
    ]
  }
}
```
> SessionStart **cannot block** and its **stdout is injected into model context** — so we emit to stderr only
> and `exit 0`. The wrapper's own interpreter check is the real guard; this hook is a courtesy warning kept fast.

---

## 6. Testing & fixtures plan (synthetic only)

### 6.1 Fixturing the binary Altium parser (the hard part)
- **Generators (committed, Foundation, pure stdlib):**
  - `tests/fixtures/_gen/altium_fixture.py` — high-level records → raw FileHeader buffer; **auto-prepends
    HEADER, auto-computes OwnerIndex** (kills the off-by-one landmine). Emits both a binary blob and a
    reviewable `.records.txt` sibling.
  - `tests/fixtures/_gen/ole_writer.py` / `cfbf_builder.py` — pack `{stream:bytes}` into a valid OLE2/CFBF,
    with a flag to force **miniFAT (<4096 B)** vs **multi-sector FAT-chain (>4096 B, ≥9 sectors)** layout, so
    both `read_mini` and `read_chain` get CI coverage (the real board uses the FAT-chain path; the env-gated
    real test never runs in CI).
- **Two synthetic `.SchDoc` containers by design:** `ole_minifat.SchDoc` and `ole_fatchain.SchDoc`; a test
  asserts identical parsed records from both.
- **Net-inference regression fixtures (hand-authored expected netlists — NEVER snapshotted from `build()`):**
  - `shared_name_label` — two same-`Text` labels on disjoint clusters (STAT/LED1 class) → assert ONE net
    `{U2.1,U3.2,R7.1,R12.1}`, zero single-pin nets there.
  - `junction_cross` — `+` crossing with a RECORD-29 dot → merge; without dot → no merge.
  - `t_junction` — wire endpoint on another wire's mid-span → merge.
  - `no_erc` — RECORD-22 marker on a deliberately open pin → suppressed.
  - `two_gnd_ports` — two same-name `GND` power ports on separate clusters → collapse to one net.
- **Malformed corpus** `tests/fixtures/malformed/`: FAT cycle, OOB sector, bogus sector_shift, huge `ndifat`,
  `mini_cutoff` bomb, truncated header, zero-length stream, missing root; deeply-nested S-expr, 10 MB atom,
  unterminated quote, symlinked lib path. `test_fuzz_safety.py` asserts each raises a **structured** error
  within a time/memory budget (stdlib `signal.alarm` + `resource.setrlimit`).
- **Edge micro-fixtures:** truncated final record; label `Text` containing `|`/`=`; CJK + Ω/µ `%UTF8%` field
  (assert clean BOM round-trip); stream sized exactly 4095 and 4096 (cutoff boundary).
- **Env-gated real-file test** `test_integration_real.py` (`AKCLI_ALTIUM_SAMPLE` path; **skips** when unset):
  asserts only **generic invariants** (parses; components>0; every named net ≥1 member; deterministic across
  two runs; JSON round-trips + validates against `netlist.schema.json`). **No solestack-specific net/pin
  names** in the public repo — those expectations live in the solestack adapter behind `AKCLI_ALTIUM_EXPECT`
  (non-committed JSON in the private repo). **Never snapshots.**

### 6.2 KiCad fixtures
- Vendored minimal symbol source `tests/fixtures/kicad/symbols/` — `Device` R/C/L + `power` GND/+3V3, incl.
  one `(extends)`-derived symbol (`C_Polarized`) — because dev/CI machine has **no KiCad libs**.
- Version-matrix fixtures: at least one **KiCad 7** and one **KiCad 8** `.kicad_sch`.
- **Gates (block all writer work until green):**
  - `test_roundtrip_byte_identity.py` — read real `.kicad_sch` → write unchanged → byte-identical.
  - `test_writer_connectivity.py` — place R/C + power port, wire pin-to-pin → `connectivity.verify` reports
    zero dangling + auto-junctions inserted; optional `kicad-cli` cross-check when available.

### 6.3 Golden/diff hygiene
- Canonicalize unnamed nets by **smallest member token** before any golden compare; order-invariance test
  (shuffled record order → identical canonical netlist).
- `.gitattributes` marks fixtures binary, golden/`.kicad_sch` text `eol=lf`; `MANIFEST.sha256` verified in CI
  to catch Windows-checkout corruption.

### 6.4 CI matrix
- **Lint/unit/fixture jobs:** OS = {ubuntu, macos, windows} × Python = {3.11, 3.12, 3.13}. Runtime is
  zero-dep; tests use `pip install -e .[dev]` (`pytest`; `jsonschema` dev-only for schema tests).
- **KiCad-cli job:** single dedicated entry **ubuntu + pinned KiCad 8.x** (heavy install; pin one major).
  Everywhere else `shutil.which`-skipif. A "no kicad-cli" job proves graceful degradation.
- **Manifest/packaging jobs:** `jq . hooks/hooks.json`; `claude plugin validate . --strict` (marketplace) +
  a separate plugin-component validation/load smoke (copy tree minus marketplace.json, validate); `test -x
  bin/akcli`; `akcli --help` from a clean checkout; `python -m build && twine check dist/*`;
  `tools/sync_version.py --check`.

---

## 7. SEO assets (single source of truth: `docs/seo.md`)

### 7.1 GitHub About (≤350 chars, exact)
> Dual-format EDA toolkit + Claude Code plugin: read Altium binary .SchDoc/.SchLib/.PcbDoc AND KiCad
> .kicad_sch with no Altium or KiCad install, then run ERC/power/pinmap/BOM checks and draw KiCad schematics.
> Zero-dependency Python CLI built for AI coding agents. Not an Altium-to-KiCad converter.

### 7.2 GitHub Topics (exactly 20, ≤50 chars, lowercase, hyphenated — no dots/underscores)
`altium, kicad, eda, schematic, pcb, netlist, schdoc, kicad-sch, erc, electronics, hardware, pcb-design,
electronic-design-automation, altium-designer, claude-code, ai-agents, cli, python, netlist-parser, circuit-design`

### 7.3 README outline (keyword H2s + file extensions + FAQ)
```
# altium-kicad-cli — read Altium .SchDoc & KiCad .kicad_sch, run ERC, draw KiCad (no EDA install)
  (first paragraph: lead with long alias + "Not an Altium-to-KiCad converter"; name akcli/altium_kicad_cli)
## What makes this different  (bullet list)
## Read Altium .SchDoc / .SchLib / .PcbDoc without Altium installed
## Parse KiCad .kicad_sch / .kicad_sym / .kicad_pcb (S-expression)
## Run ERC and design checks (power, pinmap, BOM, diff) from the command line
## Draw / write KiCad schematics (.kicad_sch) from an op-list
## How it differs from altium2kicad, SKiDL, kinparse, pykicad, python-netlist   (comparison table)
## Use as a Claude Code plugin / with AI coding agents (and MCP roadmap)
## Install (akcli CLI + plugin)
## Roadmap / Status   (unbuilt features clearly labeled; claims match shipped milestones)
## FAQ
```
**Comparison table** rows: altium2kicad, KiCad built-in Altium importer, kinparse, python-netlist, SKiDL,
pykicad, flaco/altium-mcp. Columns: Reads Altium binary .SchDoc? | Reads KiCad? | No EDA install? |
Draws/writes KiCad? | Runs ERC/design checks? | AI-agent native?

**FAQ questions (verbatim; each answer repeats the query keywords in sentence 1):**
1. How do I read/open an Altium .SchDoc file without Altium installed?
2. How do I parse a .kicad_sch file in Python?
3. How do I extract a netlist from Altium or KiCad?
4. Can I run ERC / electrical rule check from the command line without opening KiCad?
5. Is this an Altium to KiCad converter? *(No — explain, link altium2kicad / KiCad importer.)*
6. Is there an Altium MCP server / how do I use Altium with an AI agent?
7. altium2kicad / SKiDL / kinparse / pykicad alternative?
8. How do I diff two schematic versions (v1 vs v2)?
9. How can Claude Code / Cursor help with PCB schematic design?

### 7.4 pyproject keywords + classifiers (exact)
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "altium-kicad-cli"
description = "Read Altium binary .SchDoc and KiCad .kicad_sch with no EDA install; run ERC/design checks and draw KiCad. For AI coding agents."
requires-python = ">=3.11"
readme = "README.md"
license = "MIT"
keywords = ["altium","kicad","schdoc","kicad_sch","eda","schematic","pcb","netlist","erc",
            "electronic-design-automation","ole2","cfbf","s-expression","netlist-parser",
            "pcb-design","claude-code","ai-agent","circuit-design","hardware-design"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Environment :: Console",
  "Intended Audience :: Developers",
  "Intended Audience :: Manufacturing",
  "Intended Audience :: Science/Research",
  "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Operating System :: OS Independent",
]

[project.scripts]
akcli = "altium_kicad_cli.cli:main"
altium-kicad-cli = "altium_kicad_cli.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8", "jsonschema>=4", "build", "twine"]

[tool.setuptools.packages.find]
where = ["src"]
```
> `keywords` is a **list** (PEP 621), not a comma string. The EDA classifier string is exact-trove (validated
> by `twine check` in CI). Non-file SEO (About, Topics, social-preview) is applied by `tools/seo-apply.sh` via
> `gh repo edit … --add-topic …` (one per topic) — these are repo settings, not committed files.

---

## 8. Risk register + platform validity

**Exit-code table (`errors.EXIT`):** 0 success/no findings · 1 check findings present · 2 usage/arg error ·
3 parse error (corrupt OLE2/sexpr) · 4 file not found · 5 unsupported format · 6 op-list/verify failure ·
7 external tool missing. `check` is lint-style (non-zero on findings) with `--exit-zero` for report mode.

| # | Risk | Mitigation | macOS-validatable? |
|---|---|---|---|
| 1 | Net-inference defect (STAT/LED1 not merged) ships as "expected" | Rebuild net layer in `netbuild.py`; hand-authored golden; STAT regression fixture gates checks | ✅ fully (synthetic) |
| 2 | Multi-storage OLE collapse (.SchLib/.PcbDoc) | `_cfbf.read_streams_qualified` walks dir tree; per-storage tests | ✅ |
| 3 | Pin types absent/Passive → vacuous ERC pass | net-name-based power/ground + type-confidence gating + report caveat | ✅ |
| 4 | Unbounded FAT/miniFAT loops, header allocation bombs | `safety` caps + cycle detection + header validation; `test_fuzz_safety` | ✅ |
| 5 | S-expr recursion → uncatchable SIGSEGV | iterative parser, depth/atom/node caps, ban `setrecursionlimit` | ✅ |
| 6 | KiCad wires don't connect (geometry/units) | integer-nm math, pin-world snapping, `connectivity.verify` primary gate, byte-identity gate | ✅ (no KiCad needed for primary gate) |
| 7 | Non-deterministic UUIDs → non-idempotent writes | UUIDv5 from sheet-uuid+designator+op-index | ✅ |
| 8 | `(instances)` path / `#PWR` wrong → empty netlist / R? | write both legacy + instances path; flat-only v1 | ✅ |
| 9 | `bin/akcli` `$CLAUDE_PLUGIN_ROOT` empty / python 3.9 | self-locating wrapper + interpreter discovery | ✅ |
| 10 | DIFF noise (coordinate-named nets) | match by membership/UniqueID, never display name | ✅ |
| 11 | Licensing: proprietary header + false "clean-room" | relicense parser to MIT (strip `LicenseRef-Proprietary`); own schema namespace; `THIRD_PARTY_NOTICES` crediting altium-mcp chain | ✅ |
| 12 | Path traversal via lib_id / config / bridge | `safety.safe_path` allowlist; per-run 0700 bridge dir, `O_NOFOLLOW` | ✅ |
| 13 | Destructive write corrupts user schematic | snapshot+temp+fsync+verify-temp+`os.replace`, mtime lock, `--apply` required | ✅ |
| 14 | kicad-cli erc exit-code misread | never pass `--exit-code-violations`; parse JSON; advisory only | ⚠️ needs kicad-cli (CI ubuntu only) |
| 15 | PCB binary sections (Pads/Tracks) | v1 ASCII-only + guard refuses binary; binary decoders deferred | ✅ (read), ❌ verify |
| 16 | **Altium authoritative netlist / ERC / live write** | optional Windows live driver; python `bridge.py` offline-unit-testable with mocked response | **❌ Windows + Altium 22+ only** |
| 17 | DelphiScript half (`altium_api.pas/.PrjScr`) | scaffolded + iterated on user's Windows box | **❌ Windows-only/unvalidatable here** |
| 18 | Multi-sheet/hierarchical merge unvalidated (no real fixture) | synthetic multi-sheet fixtures + loud caveat | ✅ synthetic only |
| 19 | Version drift across 3 manifests | pyproject is SoT; `tools/sync_version.py` + CI check | ✅ |
| 20 | Repo public over-promises | Roadmap/Status section; flip-public gated on claims==shipped milestones | ✅ |

**Summary of platform split:**
- **Fully buildable + validated on macOS/Linux/CI:** all Altium **read/analyze**, net inference, all checks,
  report, op-list + validator, KiCad **read + write/draw** (primary connectivity gate is pure Python), CLI,
  plugin, SEO, safety/fuzz, `bridge.py` offline unit tests.
- **Cross-platform but needs `kicad-cli` (CI ubuntu + KiCad 8):** the *optional secondary* ERC verify.
- **Windows + Altium 22+ only (cannot be validated from this macOS session):** Altium authoritative
  netlist/ERC and the live write/draw driver (`altium_api.pas`/`.PrjScr`).

---

## 9. Ordered build sequence (groups → milestones)

| MS | Goal | Groups / files | Exit criteria |
|---|---|---|---|
| **0** | **Freeze Foundation** | Group **F** (all of §3.1, schemas, manifests, wrapper, fixture generators, `.gitattributes`) | `akcli --help` runs from clean checkout; `claude plugin validate . --strict` green; `twine check` green; F frozen |
| **1** | Skeleton + SEO + CI live | Group **SEO/Docs** + CI matrix | `/plugin install` works; README/Topics/About baked from `docs/seo.md`; CI matrix passing; all on-page SEO present |
| **2** | Altium read + **net fix** | Group **A** + Group **N** | STAT/LED1 alias fixture passes (one net, zero false single-pin); junction/T-junction/No-ERC/two-GND fixtures pass; both OLE-layout fixtures parse identically; fuzz corpus all structured errors |
| **3** | Analysis brain + CLI core | Group **C** + report + Group **X** (`read/net/component/check/diff/pinmap/export`) | checks run on synthetic Altium; exit codes per §8; report prints metadata caveats; DIFF matches by membership |
| **4** | KiCad read | Group **K** | synthetic `.kicad_sch` (v7+v8) parse to model with pin types resolved from `lib_symbols`; net inference shared with Altium |
| **5** | KiCad write/draw | Group **W** + `drivers/kicad_cli.py` | byte-identity round-trip gate green; `plan`/`draw --dry-run`/`draw --apply` work; connectivity gate zero-dangling; idempotent re-run |
| **6** | Libraries + PCB (partial) | `readers/altium_schlib.py`, `readers/altium_pcb.py` (ASCII), `kicad_lib.py` extensions | SchLib recovers all symbols; PcbDoc parses Nets6/Components6/Classes6/Rules6; binary sections refused loudly |
| **7** | Skill + commands + adapter | Group **S** + Group **ADP** | `/altium-kicad:circuit-{review,pinmap,draw,diff}` invoke `akcli`; `circuit-draw` has `disable-model-invocation:true`; DTS/pinout adapters feed generic `pinmap` |
| **8** | **OPTIONAL** Altium live | **8a** `drivers/altium_live/bridge.py` (offline-testable now); **8b** `altium_api.pas/.PrjScr` (Windows only) | 8a: bridge protocol + mocked response unit tests pass on macOS. 8b: validated only on user's Windows + Altium 22+ box |

**Frozen-first set (author + freeze before anything else):** `model.py, ops.py, errors.py, safety.py,
units.py, config.py, schemas/*.json, pyproject.toml, .claude-plugin/plugin.json,
.claude-plugin/marketplace.json, bin/akcli, hooks/hooks.json` + the fixture generators. Everything else codes
against these signatures and never edits them.

---

### Appendix A — Altium RECORD-ID quick reference (net-bearing marked ★)
`1` Component · `2` Pin★ · `6` Polyline · `15` SheetSymbol★ · `16` SheetEntry★ · `17` PowerPort★ ·
`18` Port★ · `22` No-ERC · `25` NetLabel★ · `27` Wire★ · `29` Junction★ · `34` Designator ·
`41` Parameter · `44/45/46/48` Implementation/Model/Footprint.

### Appendix B — Licensing posture (LOCKED)
- Repo LICENSE = **MIT**. The ported parser logic is **relicensed** (same author) — strip the
  `SPDX-License-Identifier: LicenseRef-Proprietary` header on port; record provenance in the commit/NOTICE.
- altium-mcp is used as an **independent-design reference for high-level patterns only** (file-based JSON
  bridge, a protocol-version field, structured `ERROR: CODE` strings). **No schema bytes copied** — our
  `$id`, titles, ERROR enum, and `protocol_version` are original. `THIRD_PARTY_NOTICES.md` credits both
  flaco-source/altium-mcp (2026) and coffeenmusic/Siddharth Ahuja (2025) with full MIT text. The word
  "clean-room" is replaced everywhere by *"independent reimplementation; no source copied; attribution
  retained where structures are referenced."*

(SPEC also written to `/private/tmp/claude-501/-Users-liching-yu-Documents-GitHub-solestack/014194f1-642c-4604-aa1e-8265e1f83523/scratchpad/altium-kicad-cli-SPEC.md`)