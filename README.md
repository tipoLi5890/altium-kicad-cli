**English** · [繁體中文](.github/README.zh-Hant.md) · [简体中文](.github/README.zh-Hans.md)

# altium-kicad-cli — read Altium .SchDoc & KiCad .kicad_sch, run ERC, draw KiCad (no EDA install)

**altium-kicad-cli** (CLI command `akcli`, import package `altium_kicad_cli`) is a zero-dependency
Python toolkit and Claude Code plugin that reads **Altium binary `.SchDoc` / `.SchLib` / `.PcbDoc`**
**and** **KiCad `.kicad_sch` / `.kicad_sym` / `.kicad_pcb`** with **no Altium or KiCad installed**,
runs ERC / power / pinmap / BOM / diff checks from the command line, and draws KiCad schematics from a
JSON op-list. It is built for AI coding agents.

It reads both formats into one normalized model and *analyzes* them — parse, check, diff, and draw —
giving you a scriptable, install-free workflow that an automation pipeline or an LLM agent can drive.

[![CI](https://github.com/tipoLi5890/altium-kicad-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/tipoLi5890/altium-kicad-cli/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Highlights

- **Two formats, one model.** Altium binary `.SchDoc` and KiCad `.kicad_sch` both normalize into the
  same `Schematic`/`Pcb`/`Library` model, so every check, diff, and report is format-agnostic.
- **No EDA install required.** Pure stdlib OLE2/CFBF + Altium record decoding and an iterative KiCad
  S-expression parser. No Altium, no KiCad, no compiled extensions — just Python ≥ 3.11.
- **Zero runtime dependencies.** Standard library only (including `tomllib`). Easy to vendor, sandbox,
  or run in CI.
- **Net inference you can trust.** A rebuilt net layer handles global same-name merges, junctions,
  T-junctions, and No-ERC markers — fixing the classic "same-named nets split into single-pin nets" bug.
- **Read-only on Altium, safe writes on KiCad.** Altium files are never modified offline; KiCad writes
  go through an atomic snapshot → temp → verify → replace pipeline with a pure-Python connectivity gate.
- **AI-agent native.** Ships as a Claude Code plugin with skills/commands, emits structured JSON with
  `schema_version`, and accepts a versioned op-list for deterministic, idempotent edits.

## Read Altium .SchDoc / .SchLib / .PcbDoc without Altium installed

`akcli` opens Altium binary files directly. It contains a hardened OLE2/CFBF (Compound File Binary
Format) container reader and an Altium record decoder — no Altium Designer, no Windows, no license.

```bash
akcli read   hardware/insole/main.SchDoc        # parse a .SchDoc to normalized JSON
akcli net    hardware/insole/main.SchDoc         # extract the netlist (net -> pins)
akcli component hardware/insole/main.SchDoc       # list components / designators / values
```

Supported Altium inputs: `.SchDoc` (schematic), `.SchLib` (symbol library), `.PcbDoc` (board —
ASCII `Nets6`/`Components6`/`Classes6`/`Rules6` sections in v1; binary pad/track sections are
refused loudly rather than mis-parsed). All Altium access is **read-only**.

## Parse KiCad .kicad_sch / .kicad_sym / .kicad_pcb (S-expression)

The same CLI parses KiCad's S-expression formats with an explicit-stack (non-recursive) tokenizer
that is depth-, atom-, and node-bounded — so a malformed or hostile file can't blow the stack.

```bash
akcli read hardware/board.kicad_sch              # .kicad_sch -> normalized JSON
akcli net  hardware/board.kicad_sch              # net membership, shared net engine
```

KiCad pin electrical types are resolved from `lib_symbols` at read time (instance pins carry no type),
so ERC has the data it needs. KiCad 7 and KiCad 8 files are both supported.

## Run ERC and design checks (power, pinmap, BOM, diff) from the command line

Run an electrical rule check and other design checks without opening any EDA tool:

```bash
akcli check  main.SchDoc                          # ERC-lite + power + BOM hygiene
akcli pinmap main.SchDoc -C altium-kicad-cli.toml # MCU pin -> net (+ optional expected table)
akcli diff   v1.SchDoc v2.SchDoc                   # net-membership diff, not name-based
```

Power/ground detection is **net-name + power-port based**, not purely electrical-type based, because
real boards are dominated by `Passive` pins — a naive type-only ERC produces a vacuous pass. Every
report prints a metadata header (passive-pin ratio, suppressed No-ERC count, unnamed-net count,
fractional-coordinate presence) so a clean result is never mistaken for an empty one.

## Draw / write KiCad schematics (.kicad_sch) from an op-list

`akcli` writes KiCad schematics from a versioned JSON **op-list** (place components, wires, junctions,
labels, power ports, text...). Writes are surgical and idempotent (deterministic UUIDv5), guarded by a
pure-Python connectivity verifier, and require an explicit `--apply` (default is a dry run).

```bash
akcli plan  ops.json --target board.kicad_sch     # validate op-list, show what would change
akcli draw  ops.json --target board.kicad_sch     # dry-run by default (no file written)
akcli draw  ops.json --target board.kicad_sch --apply   # atomic write + verify + backup
```

Altium *write/draw* is available only through the optional Windows live driver (Altium 22+ running);
offline, Altium is analysis-only.

## Use as a Claude Code plugin / with AI coding agents (and MCP roadmap)

Install the Claude Code plugin and your agent gets `/altium-kicad:circuit-review`,
`circuit-pinmap`, `circuit-draw`, and `circuit-diff` commands plus a circuit-design skill, all calling
`akcli` under the hood. Every command emits structured JSON (`--json`) carrying `schema_version`, and
the op-list carries a `protocol_version`, so agent output stays machine-checkable and idempotent.

A native **MCP server** for Altium/KiCad is on the roadmap (see below); today the integration surface is
the Claude Code plugin + the `akcli` CLI, which any agent can shell out to.

## Install (akcli CLI + plugin)

```bash
# CLI (recommended): isolated install via pipx
pipx install altium-kicad-cli
akcli --version

# or run from a clone, no install (zero runtime deps)
git clone https://github.com/tipoLi5890/altium-kicad-cli
./altium-kicad-cli/bin/akcli --help
```

Claude Code plugin (marketplace name `altium-kicad`):

```text
/plugin marketplace add tipoLi5890/altium-kicad-cli
/plugin install altium-kicad@altium-kicad
```

Full details and troubleshooting in [INSTALL.md](INSTALL.md). Requires **Python ≥ 3.11** (for stdlib
`tomllib`); the `bin/akcli` wrapper auto-selects a new-enough interpreter if your default `python3` is
older.

## Roadmap / Status

> **Status: pre-alpha / under active construction.** The repository currently contains the frozen
> implementation specification ([`docs/SPEC.md`](docs/SPEC.md)) and is being built milestone by
> milestone. There is **no PyPI release yet**, and the badges/commands above describe the *target*
> behavior. Treat any feature not marked **Shipped** below as not-yet-available.

| Capability | Milestone | Status |
|---|---|---|
| Foundation: model, ops, errors, safety, units, config, schemas, plugin scaffold | MS0 | In progress |
| README / SEO / docs / CI matrix | MS1 | In progress |
| Altium `.SchDoc` read + rebuilt net inference (STAT/LED1 merge fix) | MS2 | Planned |
| Checks (ERC/power/BOM/diff/pinmap) + CLI core | MS3 | Planned |
| KiCad `.kicad_sch` read (v7/v8) | MS4 | Planned |
| KiCad write/draw from op-list (connectivity gate, idempotent) | MS5 | Planned |
| `.SchLib` / `.PcbDoc` (ASCII) read | MS6 | Planned |
| Claude Code skill + commands + DTS/pinout adapters | MS7 | Planned |
| **Optional** Altium live driver (Windows + Altium 22+) | MS8 | Planned (Windows-only) |
| Native MCP server | post-1.0 | Idea / roadmap |

**Explicitly deferred (not in v1):** offline Altium *writing*; Altium-authoritative ERC/netlist (needs
live Altium); Altium `.PcbDoc` binary sections (pads/tracks/vias/arcs/fills/regions); hierarchical /
multi-sheet KiCad writing (flat-only v1). See the Risk register in `docs/SPEC.md` §8.

## FAQ

### How do I read/open an Altium .SchDoc file without Altium installed?
To read or open an Altium `.SchDoc` file without Altium installed, run `akcli read file.SchDoc` (or
`akcli net file.SchDoc` for the netlist). `akcli` is a zero-dependency Python tool that decodes the
Altium binary OLE2/CFBF container directly — no Altium Designer, no Windows, and no license required.

### How do I parse a .kicad_sch file in Python?
To parse a `.kicad_sch` file in Python, use `akcli read board.kicad_sch`, or import
`altium_kicad_cli.readers.kicad` and call `read_sch(path)`. It uses a bounded, non-recursive
S-expression parser (stdlib only) and returns a normalized `Schematic` with components, pins, and nets.

### How do I extract a netlist from Altium or KiCad?
To extract a netlist from Altium or KiCad, run `akcli net file.SchDoc` or `akcli net board.kicad_sch`.
Both formats share the same net-inference engine (`netbuild`), which merges same-named nets, junctions,
and T-junctions, and emits net → pin membership as JSON validated against `netlist.schema.json`.

### Can I run ERC / electrical rule check from the command line without opening KiCad?
Yes — you can run an ERC / electrical rule check from the command line without opening KiCad. Run
`akcli check file.SchDoc`. The ERC-lite engine is pure Python (no EDA install) and uses net-name +
power-port detection plus type-confidence gating; an optional `kicad-cli` secondary verify is used when
KiCad is available.

### What does `akcli` do with Altium and KiCad files?
`akcli` reads both Altium and KiCad files into one normalized model and lets you *analyze, check, diff,
and draw* from the command line: parse a schematic to JSON, extract a netlist, run ERC/power/BOM checks,
diff two revisions by net membership, and write KiCad schematics from a JSON op-list. Altium access is
read-only offline; KiCad writes are atomic and connectivity-verified.

### Is there an Altium MCP server / how do I use Altium with an AI agent?
A native Altium/KiCad MCP server is on the roadmap; today you use Altium with an AI agent via this
Claude Code plugin and the `akcli` CLI, which any agent can shell out to. The design references a
file-based JSON bridge pattern (credited in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)); an
optional Windows live driver drives a running Altium 22+ for write/draw.

### How do I diff two schematic versions (v1 vs v2)?
To diff two schematic versions (v1 vs v2), run `akcli diff v1.SchDoc v2.SchDoc`. The diff matches nets
by **membership** (Jaccard) and components by UniqueID / signature — not by display name — so renamed or
coordinate-named nets don't show up as spurious changes.

### How can Claude Code / Cursor help with PCB schematic design?
Claude Code or Cursor can help with PCB schematic design by calling `akcli` to read your `.SchDoc` /
`.kicad_sch`, run ERC/power/pinmap/BOM checks, diff revisions, and draw KiCad schematics from a JSON
op-list. The Claude Code plugin exposes `/altium-kicad:circuit-review`, `circuit-pinmap`,
`circuit-draw`, and `circuit-diff` for exactly this workflow.

---

## Acknowledgments

`akcli jlc` is powered by other people's open-source work, used **at arm's length** (no
source imported or vendored — see [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)):

- **nlbn** and **npnp** by **linkyourbin** (both **Apache-2.0**) — invoked as subprocesses
  to convert an LCSC part into a KiCad (`nlbn`) or Altium (`npnp`) library.
- **jlcsearch** (tscircuit, MIT) and **jlcparts** (MIT) — the part-search backend.
- **EasyEDA / LCSC / JLCPCB** — the component data source (unofficial, read-only metadata
  lookup; conversion delegated to nlbn/npnp).

Full attribution and license texts: [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## Contact

Questions, bugs, or feature requests: please [open a GitHub issue](https://github.com/tipoLi5890/altium-kicad-cli/issues).

---

## License

MIT © 2026 Li, ching yu. See [LICENSE](LICENSE). Third-party attribution (the JSON bridge pattern chain,
plus the MS10 nlbn/npnp/jlcsearch acknowledgments) is recorded in
[ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Security
model and enforced limits are documented in [SECURITY.md](SECURITY.md).
