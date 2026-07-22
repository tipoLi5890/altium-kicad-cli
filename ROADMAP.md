# Roadmap

`akcli` is an **AI-native KiCad design agent**: an LLM (or a plain CI pipeline) authors and edits
`.kicad_sch` from a versioned JSON op-list behind net-diff safety rails, verifies the result with
checks it can gate on, **runs an advisory engineering design review**, simulates it on KiCad's
bundled ngspice, sources real parts, and imports Altium `.SchDoc`/`.SchLib`/`.PcbDoc` into the same
normalized model — a zero-dependency (pure-stdlib Python) toolchain, purpose-built for KiCad.
Every output is typed, versioned,
and machine-checkable, because the primary user is an agent shelling out from a pipeline.

KiCad is the writable target and the sole development line. Altium is an **import source** — a
read-only on-ramp into the KiCad flow, not a symmetric conversion peer. That repositioning
(2026-07) reshaped this roadmap: the Altium-interop items that earlier milestones treated as
release-critical now live in a demand-driven optional track, and the experimental Windows live
bridge is **shelved indefinitely**.

## Where we are (v0.13.0)

Shipped and working today (details per release in [CHANGELOG.md](CHANGELOG.md)):

- **KiCad authoring:** `plan`/`draw` from a `protocol_version 1` op-list — **22 ops + 10 macros**
  (incl. hierarchical `add_sheet`, `rename_net`, cascade delete, multi-unit placement, `mid()`
  anchors), `akcli new` blank-sheet bootstrap, deterministic UUIDv5 idempotency, atomic apply with a
  rotated backup stack (`undo --list`/`--steps`), a pure-Python connectivity gate, a before/after
  **net-membership diff** on every run, and `--apply --strict-nets` refusing named-net
  splits/merges. **Net-preserving re-layout** (0.8.0): `move_component` carries a part's net labels
  and wire endpoints (`carry_labels`/`carry_wires`), and `arrange --groups` relocates whole
  functional blocks as rigid bundles; `library check-lock` refuses a write under an open KiCad GUI.
  `relink-symbols` refreshes stale embedded libraries behind a net-equivalence gate.
  **Modular authoring (v0.10)**: functional-group envelope with group-local coordinates and a
  persisted `Group` property, `akcli groups`/`--frame` self-refreshing module borders,
  bare `arrange --groups --frames`, relative placement (`anchor`+`offset_mil`), `place_array`,
  pin-safe `route_net` L/Z auto-routing, `add_rectangle`/`add_text_box` annotation graphics with
  stable `key`s, `set_title_block`, `akcli bbox` spacing planning, `plan/draw --render` look-
  before-apply previews and `render --grid` coordinate overlays, plus group layout lints.
- **Verification:** ERC-lite / power / BOM / nets / geometry / layout / libsync checks,
  **design-intent assertions** (`nets --intent-snapshot` → `check --intent`, per-net modes +
  wildcards), checker-agnostic `[[waiver]]` config + `--fail-on`, SARIF/JUnit output, structured
  `pos`/`anchors` on findings. Net inference is **arbitrated against `kicad-cli`'s own netlister**
  (a standing parity harness incl. rotation/mirror transforms, label scoping, buses, hierarchy).
- **Design review (0.8.0):** `akcli review analyze|report|explain|facts|propose|testbench|diff|tree|validate`
  — an advisory engineering-review engine on the normalized model (so it reviews Altium `.SchDoc`
  as readily as `.kicad_sch`). Six detector families (signal / validation / pcb / emc / domain /
  gerber; **44 rules**) emit **confidence-graded** findings (deterministic / heuristic /
  datasheet_backed / llm_reviewed) with an evidence envelope published as `findings.schema.json`.
  A **datasheet facts store** (`review facts`, PDF sha256+page pinned) upgrades findings to
  datasheet_backed; `review propose` recomputes + E-series-snaps fixes into op-list/contract/sim
  drafts (never touching a file — they go back through `plan → draw`); `review validate` gates LLM
  candidates (four checks, quarantine); `review diff`/`tree` add fingerprint-aligned drift and a
  power tree. Advisory by default — the only blocking path is `release preflight --review-policy`
  (a calibrated allowlist). Guide: [docs/review-rules.md](docs/review-rules.md).
- **Design integrity:** design **contracts** (`check --contract` — require/forbid
  pin-net & pin-pair topology, component values, NC pins, owned/expiring exceptions), schematic ↔
  PCB **equivalence** (`verify sch board.kicad_pcb` — pad-net partition, refdes, footprint), the
  **`library`** workspace (audit/repair/import-altium/check-lock — fixes the footprint-nickname &
  3D-path traps, dry-run→apply), versioned **`fab`** profiles (`fab check`/`explain` — free-via
  envelope, tenting, via-in-pad, cost thresholds, order manifest), and a **`release preflight`**
  gate emitting a traceable manifest (with `--review-policy` and `--gerbers` gates in 0.8.0).
  Guide: [docs/design-integrity.md](docs/design-integrity.md).
- **Simulation:** `akcli sim` — schematic → SPICE deck → KiCad's bundled libngspice in a
  crash-isolated, timeout-killed child; `sim.json` assertions (two-sided bounds, multi-analysis),
  `--sweep` corner matrices, `--deck-only` engine-free mode, floating-node detection with
  auto-`rshunt`, `fit-diode` datasheet fits written back to KiCad-native `Sim.*` fields.
- **Parts & manufacturing:** `jlc search`/`show`/`add` (in-process LCSC → KiCad conversion),
  `jlc bom` purchasability with qty tier pricing + JLCPCB order-CSV export + confidence-gated
  `--fix`, `jlc datasheet` PDF resolution/fetch (whole-BOM batch, `--resolve-mpn`) — which now
  feeds the review facts store.
- **Calculators:** `akcli calc` — 60 standards-cited engineering calculators, engineering-notation
  inputs, `--ops` bridge into op-lists (also the engine the review layer recomputes fixes through).
- **Readers:** KiCad 7–10 S-expression (bounded, non-recursive, hierarchical) incl. **deep
  `.kicad_pcb`** (pad-net bindings, tracks/vias/zones, board setup); Altium binary `.SchDoc`
  (multi-sheet + `.PrjPcb`), text-record `.SchLib`, `.PcbDoc` ASCII sections **plus binary copper**
  (`Tracks6`/`Vias6`/`Arcs6`/`Pads6`, cross-validated against KiCad's importer), **`.PcbLib`**
  footprint libraries → `FootprintDef`/`FootprintPad` (also `.kicad_mod`/`.pretty`), and a
  **RS-274X/Excellon gerber** directory reader (0.8.0) feeding the fab-package checks.
- **Agent surface:** Claude Code / Codex plugin (`akcli`), 12 skills, 5 slash commands, `akcli view`
  dashboard (hub + calc + live watch with SSE, ERC markers, lint overlay, BOM panel), stable exit
  codes 0–8, `schema_version`-stamped JSON, and a `--json` error envelope (`{"error": {code,
  message, exit, remediation}}`) on every failing exit path so stdout always parses as JSON even
  on failure. `akcli --version` reports the code actually running (a
  source checkout's `pyproject.toml` wins over stale installed metadata). 0.9.0 additions:
  `akcli capabilities` (the self-describing surface manifest), `akcli render` (pure-stdlib SVG),
  the workspace write journal + `akcli log`, `akcli ops validate` + a PreToolUse draw guard,
  `read --summary`/`nets --match`/`--limit` output throttling, and structured per-op
  `remediation` hints. 0.12.0 additions: `akcli doc` (the pinout book), the `.akcli/` workspace
  state root (journal + rotated undo backups + `--note` design-intent records,
  [docs/agent-state.md](docs/agent-state.md)), 2D side-by-side group packing
  (`arrange --groups --page-width`, `[arrange]` policy, `[check] group_clearance`), and the
  enforced net-preservation gate on `arrange --groups --apply`. 0.13.0 additions:
  `arrange --groups --propose-labels` (the refusal -> label-on-pin repair-draft loop, proven on a
  real 88-part board now in the corpus), collision-free two-phase group moves, bare
  `check --intent` via `[paths] intent`, the `doctor` workspace probe, config-surface/schema-table
  conformance gates, and agent-eval task 07 (safe re-pack post-check).
- **Quality gates:** ~2 600 tests (parser fuzzing, round-trip netlist properties, live ngspice in
  CI, Windows/macOS/Linux × Python 3.11–3.14), ruff + mypy (parts/ + calc/), a
  **docs-conformance gate** (every documented command line and count claim is executed/asserted in
  CI), wheel-install smoke, tag-driven GitHub Releases.

Honest limitations:

- **Binary `.SchLib` symbol records are refused loudly** (exit 5); only text-record libraries read.
- **`.PcbDoc` `Fills6`/`Regions6`/`Texts6`/`Polygons6` are skipped**, not parsed.
- **The Altium live bridge is an unvalidated scaffold** (Windows + Altium 22+; no CLI entry point,
  no CJK text, parameters/footprints not applied). **Shelved indefinitely (2026-07)** — the code
  and its record stay in the frozen optional track; it is not a milestone and is not promoted.
- **ERC power checks are net-name + power-port based by design.** The pin-type conflict
  matrix shipped in 0.9.0 (`ERC_PIN_CONFLICT` — the high-signal cells of KiCad's default
  matrix — plus `ERC_POWER_IN_UNDRIVEN`), type-confidence-gated like every type-based rule;
  the remaining KiCad matrix cells (unspecified-vs-anything etc.) are deliberately not
  flagged (documented in `checks/erc.py`).
- ~~`diff`/`pinmap` findings have no published JSON Schema~~ — closed post-0.8.0: every JSON
  payload family now ships a canonical schema (`diff`/`pinmap`/`draw-result` joined
  `findings`/`netlist`/`schematic`/`ops`/`sim`/`proposals`/`datasheet-facts`), all mirrored
  byte-identically into the wheel and CI-gated.
- **PDN impedance / anti-resonance is not built** — the EMC review is a pre-compliance risk
  analyzer (never a compliance verdict). Stdlib SVG rendering shipped in 0.9.0 as
  `akcli render` and draws faithful symbol artwork from the embedded `lib_symbols` on KiCad
  sources (post-0.13); Altium sources and multi-unit parts fall back to synthesized bodies,
  and `view live`'s canvas still renders through the optional `kicad-cli`.
- **Not on PyPI — by decision** (2026-07): distribution is GitHub Releases; the release workflow
  already supports PyPI trusted publishing whenever that decision changes.
- **MCP server: deferred by decision** — agents drive the plain CLI today.

## Guiding principles

1. **KiCad is the writable target; Altium files are never modified.** No code path writes an
   Altium file on disk. (The only Altium write path ever considered — the live bridge, shelved
   indefinitely — would drive a *running* Altium Designer, never a file.)
2. **Verify everything.** Dry-run by default, `--apply` is explicit and atomic, every write is
   re-read, connectivity-gated, and net-diffed; a "0 findings" report always carries its metadata
   caveats. New write capabilities land together with their verification step — and where external
   ground truth exists (`kicad-cli`, ngspice), akcli's own engines are arbitrated against it.
3. **Advisory review, earned gating.** Review findings carry explicit confidence and never block a
   release except through a calibrated, explicitly-approved policy allowlist; a finding that leans
   on a datasheet number cites its PDF sha256+page, and one that lacks evidence says so
   (`insufficient_evidence`) rather than guessing.
4. **Zero runtime dependencies.** Python ≥ 3.11 stdlib only. Network code stays isolated under
   `akcli jlc`; `kicad-cli`/libngspice/`pdftotext` remain optional, discovered, and advisory.
5. **Docs that cannot drift.** Every documented command, flag, and count is exercised against the
   real CLI in CI (the docs-conformance gate). Agent-facing contracts (`schema_version`,
   `protocol_version`, exit codes) change only with a changelog entry.

## Shipped milestones (what actually happened)

The original v0.2–v0.6 plan and reality diverged: the planned "v0.5 Altium alive / v0.6 ecosystem"
arc was displaced by KiCad-native depth that proved more valuable in real design sessions. The
honest history:

| Version | Theme that actually shipped |
|---|---|
| v0.2.0 | Editing ops (delete/move/multi-unit), hierarchical KiCad read, agent-contract fixes |
| v0.3.x | Altium multi-sheet + `.PrjPcb`, `expected` adapters, SARIF/JUnit, binary `.PcbDoc` copper |
| v0.4.0 | the calculator pack (60 today) + akcli-design-calc skill, unified `view` dashboard, verify/undo, macro ops, nets check, `jlc bom` |
| v0.5.0 | **Safety-rail release:** net-diff + `--strict-nets`, intent assertions, `mid()` anchors + new macros, `relink-symbols`, `jlc datasheet`, waivers + `--fail-on`, structured finding positions, cli decomposition, transform/netbuild parity fixes, `new` + multi-level undo, bus netlist semantics, ~55× netbuild speedup |
| v0.6.0 | **Simulation release:** `akcli sim` (deck/engine/models/assertions/sweeps/fit-diode), docs-conformance gate, bus aliases, `--resolve-mpn`, mypy calc/, live ngspice in CI |
| v0.7.0 | **Identity release:** project renamed to `akcli` (KiCad-first repositioning), `akcli doctor` + akcli-setup skill, `akcli-` prefix on all skills, JLCPCB manufacturing-handoff docs, one kicad-cli discovery ladder, docs gate widened to INSTALL/ROADMAP, README restructured KiCad-first |
| v0.8.0 | **Design review release:** the `akcli review` engine (M1–M9 below — signal/validation/PCB/EMC/domain/gerber detectors, datasheet-facts store, propose/diff/tree, deep-review gate, gerber package checks), design-integrity suite (contracts, sch↔PCB `verify`, library workspace, fab profiles, `release preflight`), deep `.kicad_pcb` + Altium `.PcbLib` reading, net-preserving re-layout (`arrange --groups`, `move_component` carry), `library check-lock`, `findings.schema.json`, and the working-tree-authoritative `--version` fix |
| v0.9.0 | **Agent-contract release:** capabilities manifest (+op constraints, altium_live_wired honesty), QUERY_MISS exit 8, output throttling (`read`/`nets`/`component` `--match`/`--limit`, `read --summary`), write journal + `akcli log`, `ops validate` + PreToolUse draw guard, published diff/pinmap/draw-result schemas, `--fail-on` everywhere, remediation on ALL error codes, `--json` error envelope on every exit path, universal `schema_version` stamps (AST-enforced), `akcli render` SVG, ERC pin-conflict matrix, `check --pairs`, `draw --no-erc`, `/circuit-parts`, golden corpus + review-calibration baseline in CI, sim behavioral models + solver-trap diagnostics, `review testbench`, and the agent-loop eval harness (`tools/agent_eval/`) |

## v0.8.0 — Design review release (shipped)

A native `akcli review` capability finding the engineering risks structural checks cannot express —
built on the normalized model (so every rule reviews Altium `.SchDoc` too), advisory by default,
findings carrying explicit confidence + evidence with literature citations, and the fix path staying
behind the existing `propose → plan → draw` safety rails. The whole track (M1–M9) shipped together
in 0.8.0. Per-rule specification and provenance: [docs/review-rules.md](docs/review-rules.md).

- [x] **M1 — foundation:** `Finding` evidence envelope (confidence/evidence/fingerprint/
      status), `findings.schema.json` + wheel mirror, SARIF v2 wording-immune fingerprints,
      markdown renderer, `review analyze|report|explain` CLI skeleton
- [x] **M2 — signal detectors:** divider (feedback Vref plausibility, tap-name
      mismatch), RC cutoff (via `calc rc`), crystal load caps, connector ESD/TVS coverage,
      op-amp gain topology (non-inverting/inverting/buffer/open-loop) — five fixture classes each,
      KiCad+Altium format-agnostic contract (the fuse-sizing / reverse-polarity backlog
      closed post-0.13 as `signal.power_protect`)
- [x] **M3 — validation detectors + BOM:** I²C pull-up window (missing/strong/weak/
      mismatch via `calc i2c-pullup`), cross-voltage-domain signals (level-shifter aware),
      floating enable pins; MPN-coverage sourcing audit into `check --bom` (backlog: SPI/UART
      pull-up rules, full sequencing → M7 power tree)
- [x] **M4 — datasheet facts store:** versioned facts schema (`datasheet-facts` 1.0,
      wheel-mirrored) + `review facts add|verify|lookup`, PDF sha256+page binding
      (`jlc datasheet` supplies the PDFs), optional `pdftotext` driver for quote verification;
      divider Vref / crystal CL / vdomain abs-max upgraded to `datasheet_backed`
- [x] **M5 — PCB detectors + thermal:** copper-island union-find (layer-aware,
      zone-bbox merge), unrouted-net detection, decap distance, exposed-pad thermal vias,
      IPC-2221 trace ampacity, junction-temperature estimation (facts-backed θ_JA with
      typical-package fallback) — DFM scoring deliberately left to `fab check` (single
      policy source)
- [x] **M6 — EMC rules:** eight rules across the geometric / analytical /
      stackup batches (plane presence+coverage, via stitching, edge + clock-edge routing,
      diff-pair skew, TVS placement, adjacent signal layers), every threshold a stated
      assumption; advisory `emc` metadata block (risk score + probe points + the standing
      not-a-compliance-verdict note). PDN impedance/anti-resonance stays on the backlog
      (needs zone polygons / SPICE)
- [x] **M7 — closed loop:** `review propose` (values recomputed + E-series-snapped
      via `calc eseries`; op-list/contract/sim drafts; schema-enforced "unconfirmed ⇒ no
      op-list"; layout fixes stay manual — akcli writes schematics only), `review diff`
      (fingerprint-aligned drift, `--fail-on-new`), `review tree` (rails → regulator via FB
      divider → consumers). The auto-generated subcircuit SPICE testbenches from this
      backlog **shipped in 0.9.0** as `review testbench` (RC corner + divider-ratio
      generators, cone extraction, recomputed bounds, ngspice verdicts). Backlog: full
      what-if parameter sweeps
- [x] **M8 — deep-review gate + blocking policy:** `review validate` (four
      deterministic gates, failures quarantined with reasons, accepted = `llm_reviewed`
      observations), `release preflight --review-policy` (explicit allowlist is the only
      blocking path; policy hash in the manifest), first domain family (USB-C CC
      termination), `tools/corpus_replay.py` calibration harness. Backlog (demand-ordered):
      RF/Ethernet/HDMI/memory/BMS/motor families; lifecycle audit via optional distributor
      drivers (`jlc bom` already covers LCSC purchasability)
- [x] **M9 — Gerber:** RS-274X/Excellon directory reader (X2 role detection,
      never-guess coordinate handling) + package checks (completeness, stackup count,
      registration, mixed units, outline staleness vs the board file) wired into
      `review analyze --gerbers` and a `release preflight --gerbers` gate

Three plugin skills teach the agent half of the loop: `akcli-datasheet-facts` (PDF → audited facts),
`akcli-deep-review` (candidate generation gated by `review validate`), and `akcli-release-gating`
(preflight + calibrated blocking policy).

## Milestones ahead

### v0.9 — Agent contract completeness & deeper verification (shipped as 0.9.0)

Goal: close the remaining "an agent can drive it blind" gaps, and grow `check` from ERC-lite toward
a tunable rule engine reaching across artifacts.

- [x] Publish `diff.schema.json`, `pinmap.schema.json`, and a draw-result schema,
      `schema_version`-stamped and mirrored into the package like the existing schemas —
      **shipped in 0.9.0**, plus the previously-missing `netlist`/`schematic` wheel mirrors
      and one `$id` host across all eleven schemas (M)
- [x] Machine-detectable misses: `found: false` + exit `8` (`QUERY_MISS`) for `net <file> NAME`
      and `component <file> REF`; frozen `BRIDGE_BUSY`/`BRIDGE_TIMEOUT` codes — **shipped
      post-0.8.0** (S)
- [x] `/circuit-parts` slash command wiring `jlc search → show → add → plan → draw` into one
      documented, stage-gated flow — **shipped in 0.9.0** (S)
- [x] PreToolUse hook in the plugin: `akcli ops validate` blocks a structurally invalid
      `draw --apply`; a missing prior `plan` (checked against the workspace journal) warns —
      **shipped in 0.9.0** (S)
- [x] Honest flags: `draw --no-erc` skips the advisory `kicad-cli` run (logged, never
      silent) and every failed op carries a machine-readable `remediation` field —
      **shipped in 0.9.0** (S)
- [x] ERC pin-type conflict matrix (`ERC_PIN_CONFLICT` — the high-signal KiCad cells — and
      `ERC_POWER_IN_UNDRIVEN`) behind the typed-pins confidence demotion — **shipped
      post-0.8.0**; the remaining matrix cells are documented non-goals in `checks/erc.py` (M)
- [x] Differential-pair / bus continuity checks (`check --pairs`, default-on): `PAIR_INCOMPLETE`
      (asymmetric — a lone `_N`/`_L` active-low name never fires), `PAIR_PIN_MISMATCH`, `BUS_GAP`;
      configurable via `[check]` `pairs`/`pair_suffixes`/`bus_min_family` — **shipped
      post-0.8.0**; the review EMC layer keeps the geometric *skew* detector (M)
- [x] Golden-file regression corpus: frozen `nets`/`check`/`diff`/`review`/`render` snapshots
      over the committed fixture boards, byte-compared in CI
      (`tests/golden/` + `tools/golden_regen.py`) — **shipped in 0.9.0**; growing it with
      real-world boards stays open (M)
- [x] Sim deepening — `AKCLI_OPAMP` + `AKCLI_NMOS_SW`/`AKCLI_PMOS_SW` (engine-validated in
      CI), the `SIM_ZERO_PASSIVE`/`SIM_STIMULUS_SHORTED` solver-trap warnings, and
      **`review testbench`** — **shipped in 0.9.0**; the waveform panel in the `view`
      dashboard is deferred by decision (2026-07) (M)

- [x] `--json` machine-readable failure envelope on every exit path (code recovery from
      wrapped errors, remediation for every code incl. EXIT pseudo-codes) — **shipped in 0.9.0** (M)
- [x] Universal `schema_version` stamps on every JSON object payload, enforced behaviorally AND
      mechanically (AST scan) in CI — **shipped in 0.9.0** (S)
- [x] Review-rule calibration baseline replayed in CI (`tools/corpus_replay.py` +
      `tests/golden/corpus_replay_baseline.json`) — **shipped in 0.9.0** (S)
- [x] Agent-loop eval harness (`tools/agent_eval/` — eight ground-truthed design tasks, scored
      through the real safety rails; references CI-pinned at 100%) — **shipped in 0.9.0** (M)

**Exit criterion:** a schematic PR can be gated end-to-end (check + review + diff + intent + sim
assertions), and a false finding is tuned or waived in config rather than ignored.

### v0.10 — See the circuit

Goal: humans reviewing agent work get visuals and documents, not just JSON.

- [x] Pure-stdlib SVG schematic rendering from the normalized model (components, pin tips, wires,
      junctions, labels) for stdlib-only before/after review — **shipped in 0.9.0 as
      `akcli render`** (connectivity-true, per-sheet blocks, deterministic); **faithful symbol
      artwork shipped post-0.13** (`render_art` walks the embedded `lib_symbols` graphics through
      the net engine's own transform chain; synthesized-body fallback for Altium/multi-unit); a
      `view live` integration stays open (L)
- [x] `akcli doc <file> -o book.md`: pinout book composing per-IC/connector pin tables, rail
      summary (from `review tree`), and BOM — **shipped in 0.12.0** (deterministic Markdown +
      `--json`; `--refs` widens the pin-table set) (M)
- GitHub Action and the `view` waveform panel — **deferred by decision (2026-07)**, see below.

**Exit criterion (met in 0.12.0):** `/circuit-draw` can show a human what it placed without any
EDA install (`render` + `doc`), and a design review can start from a generated pinout book.

### v1.0 — Contracts frozen, released

Goal: the public surface is stable enough to promise.

- [ ] Contract freeze audit: `schema_version`/`protocol_version` review, deprecation policy
      documented; extend the docs-conformance gate to the frozen contracts (S)
- [ ] First PyPI release (`pip install akcli`) — **gated on reversing the standing "GitHub
      Releases only" decision**; the tag-driven workflow already supports trusted publishing (S)

**Exit criterion:** every documented command, flag, exit code, and schema is covered by a test
that fails on drift — and installation is a one-liner on the chosen channel.

### Review backlog (demand-ordered)

Extensions to the shipped review engine, pulled in when real boards need them:

- [ ] More domain families: RF, Ethernet, HDMI, memory, BMS, motor (each its own detector module).
- [ ] PDN impedance / anti-resonance and plane-void EMC rules (need zone polygons / SPICE).
- [ ] Lifecycle/obsolescence audit via optional DigiKey/Mouser drivers (`jlc bom` covers LCSC today).
- [ ] Additional signal/validation rules: SPI CS counts, UART voltage-domain pairing, full
      power-sequencing analysis. (Fuse sizing + reverse-polarity shipped post-0.13 as
      `signal.power_protect` — `calc fuse-derating`-backed sizing, entry-chain walk,
      calibrated on the `power_entry` corpus board.)

### Optional track — Altium interop (demand-driven, currently frozen)

These items were milestone-critical under the old "bridge" positioning; after the KiCad-first
repositioning they proceed only if real usage pulls them:

- [ ] Binary `.SchLib` symbol decoder (pins + basic graphics) so vendor libraries read instead of
      exiting 5 (L) — prerequisite for offline `.SchLib → .kicad_sym` conversion with a fidelity gate (L)
- [ ] `.PcbDoc` remaining binary sections: fills/regions/texts/polygons (L)
- [ ] Altium `Bus`/`BusEntry` records into `netbuild` (M)
- [ ] Live bridge graduation — **shelved indefinitely (2026-07)**, kept only as a record:
      `draw --live` CLI wiring, DelphiScript validation on Windows + Altium 22+, automatic
      post-apply netlist re-export + diff (L)
- [ ] Real-AD-scale validation of sheet-entry positions in multi-sheet `.PrjPcb` reads (M)

### Deferred by decision

- **Altium live bridge** (2026-07) — **shelved indefinitely**. The Windows scaffold and its tests
  stay in the tree as a record, but graduation work is not planned and the feature is not
  promoted; KiCad is the sole development line.
- **MCP server** (`akcli mcp`) — the plain CLI + plugin skills serve agents today; revisit on demand.
- **PyPI publishing** — see v1.0; the mechanism is built, the decision is deliberate.
- **GitHub Action** (2026-07) — check/review/diff + SARIF on schematic PRs. The CLI side (SARIF
  output, exit codes, `--fail-on`) is complete; a workflow YAML can be added the day a repo
  actually gates PRs. Shelved until then.
- **`view` waveform panel** (2026-07) — sim runs and assertions work headless; the dashboard
  visualization is deferred until interactive waveform inspection is actually needed.

## Theme tracks

| Track | v0.8 (shipped) | v0.9–v0.10 | v1.0 / optional |
|---|---|---|---|
| **KiCad authoring & safety** | `arrange --groups`, `move_component` carry, `check-lock` | PreToolUse hook, honest flags | contract freeze |
| **Verification & checks** | `findings.schema.json`, sch↔PCB `verify` | diff/pinmap schemas, ERC matrix, diff-pairs, golden corpus | frozen contracts in CI; GitHub Action (deferred) |
| **Design review** | full engine M1–M9 (signal/validation/pcb/emc/domain/gerber, facts, propose/diff/tree, validate, `--review-policy`) | more domain families, PDN/EMC depth | lifecycle drivers |
| **Simulation** | — | behavioral models, review testbenches | waveform panel (deferred) |
| **Review UX** | `review tree`, markdown/SARIF reports | stdlib SVG render, pinout book | — |
| **Parts & manufacturing** | facts store from `jlc datasheet` | `/circuit-parts` command | — |
| **Altium import** | `.PcbLib` reading | — | frozen optional track (SchLib decoder, PcbDoc sections; live bridge shelved) |

## Non-goals

- **Offline Altium writing.** akcli never modifies a `.SchDoc`/`.SchLib`/`.PcbDoc` on disk. Altium
  writes, if ever, go exclusively through the (indefinitely shelved) live bridge into a running
  Altium Designer.
- **Symmetric Altium↔KiCad conversion.** Altium is an import source. Library-level conversion with
  a fidelity gate stays in the optional track; "convert my whole board pixel-perfect" is out.
- **Replacing full EDA tools.** No interactive editor, no autorouter, no autolayout — akcli reads,
  checks, reviews, simulates, and makes surgical, verifiable edits; KiCad remains the design environment.
- **A compliance predictor.** The EMC review is a pre-compliance *risk* analyzer that states its
  assumptions; only a calibrated measurement in an accredited lab establishes regulatory compliance.
- **Pixel-perfect visual fidelity.** The SVG renderer targets *reviewable*, connectivity-true
  drawings: it draws the real symbol artwork where the source carries it (KiCad `lib_symbols`),
  but does not reproduce either tool's canvas (fonts, exact text metrics, sheet decorations).
- **Becoming a dependency-heavy platform.** No third-party runtime packages, no always-on network
  features. `akcli jlc` stays the only networked surface.
