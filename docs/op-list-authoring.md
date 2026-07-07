# Op-list authoring guide

An **op-list** is the JSON document `akcli plan` / `akcli draw` execute against
a KiCad schematic. This guide is the practical companion to the formal schema
(`schemas/ops.schema.json`) and the per-executor support matrix
(`schemas/ops.capabilities.json`). Scaffolding helpers:

```bash
akcli ops list                    # the 16-op vocabulary + required fields + executor support
akcli ops template place_component        # fill-in JSON skeleton (all fields)
akcli ops template add_wire --required-only
```

## Envelope

```json
{
  "protocol_version": 1,
  "target_format": "kicad",
  "target_file": "board.kicad_sch",
  "ops": [ ... ]
}
```

- `protocol_version` is checked first; an executor rejects a higher major with
  `PROTOCOL_MISMATCH` rather than guessing.
- `target_file` may be overridden by the CLI's positional target.

## Coordinate contract (memorize this)

- **mils**, origin **top-left**, **+Y down**, snapped to the **50-mil grid**.
- Rotation is the enum `{0, 90, 180, 270}`; mirror `{none, x, y}`.
- A `"REF.PIN"` endpoint (e.g. `"U1.3"`) snaps to that pin's **exact world
  coordinate** — prefer it over raw `[x, y]` whenever a wire meets a pin.
- Wire `vertices` must form orthogonal segments; dogleg through an
  intermediate `[x, y]` when two pins don't share an axis.

## The vocabulary

Required fields per op are what the validator enforces; everything else is
optional. Run `akcli ops template <op>` for a full skeleton.

| Op | Required | Notes |
|---|---|---|
| `place_component` | `lib_id, designator, x_mil, y_mil` | optional `unit` places ONE unit of a multi-unit part (each unit is its own instance sharing the designator); `value`/`footprint` set the properties; the symbol must resolve from `--symbols`/config/`symbol_source` |
| `set_component_transform` | `designator` | rotation/mirror of an existing instance |
| `set_component_parameters` | `designator` | `reference`, `value`, `footprint`, free-form `parameters` map |
| `add_wire` | `vertices` | even, orthogonal list of `[x,y]` / `"REF.PIN"`; one segment per consecutive pair |
| `add_bus` | `vertices` | as `add_wire`, bus graphics |
| `add_junction` | `at` | usually unnecessary — the executor auto-inserts junctions at 3+-way meets and pin taps |
| `add_no_connect` | `pin` | `"REF.PIN"` or `[x,y]` |
| `add_net_label` | `name, at` | `scope: local\|global\|hierarchical` (writer is flat — avoid `hierarchical`) |
| `place_power_port` | `lib_id, net_name, at` | auto-allocates the `#PWR` reference; merges by name everywhere |
| `place_gnd` / `place_vcc` | `at` | sugar over `place_power_port` |
| `add_bus_entry` | `at` | optional `size` (default 2.54 mm @ 45°) |
| `add_text` | `text, at` | the only graphic op; optional free `angle` |
| `delete_component` | `designator` | removes ALL instances; attached wires are left for the connectivity gate to flag — delete them explicitly (`delete_object`); absent target = replay-safe no-op |
| `delete_object` | `uuid` | remove ONE top-level object (wire/label/junction/text/...) |
| `move_component` | `designator, x_mil, y_mil` | one instance (optional `unit`); its properties travel along; wires do NOT stretch |

## Execution pipeline (what happens to your ops)

1. `akcli plan <target> --ops ops.json` — validate + resolve, print what would
   change. Never writes.
2. `akcli draw <target> --ops ops.json` — **dry-run by default**: per-op
   results plus the connectivity verification.
3. `... --apply` — atomic snapshot → temp → verify-on-temp → `os.replace`,
   with a `<target>.bak` alongside. Any op error or connectivity ERROR
   (`DANGLING_ENDPOINT`, `DUPLICATE_UUID`, `UNRESOLVED_LIB_ID`, ...) refuses
   the write (exit 6).
4. Re-read after applying (`akcli net` / `akcli component`) — an exit-0 apply
   proves the write landed, not that intent was met.

## Idempotency rules

- Created nodes get deterministic UUIDv5 keyed on the root sheet uuid plus
  `designator:op_index` (or tag:coords). **Replaying the same op-list file
  converges byte-identically after one apply.**
- Because identity includes `op_index`, never reorder or insert ops mid-list
  in a file you already applied — extend with a NEW delta op-list instead.
- Deletes are replay-safe no-ops when the target is already gone.

## Worked example

```json
{ "protocol_version": 1, "target_format": "kicad", "target_file": "board.kicad_sch",
  "ops": [
    { "op": "place_component", "lib_id": "Device:R", "designator": "R1",
      "x_mil": 2000, "y_mil": 1000, "value": "10k" },
    { "op": "place_gnd", "at": [2000, 1200] },
    { "op": "add_wire", "vertices": ["R1.2", [2000, 1200]] },
    { "op": "add_net_label", "name": "SENSE", "at": [2000, 850], "scope": "global" },
    { "op": "add_wire", "vertices": ["R1.1", [2000, 850]] }
  ] }
```

More patterns (LDO block, decoupling, connector fanout, multi-unit gates) live
in the `schematic-authoring` skill.
