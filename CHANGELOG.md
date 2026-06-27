# Changelog

All notable changes to `altium-kicad-cli` are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Versioning policy

`altium-kicad-cli` ships **three** version numbers; this section is their contract.

- **Package version (SemVer `MAJOR.MINOR.PATCH`).** The single source of truth is
  `pyproject.toml`; `tools/sync_version.py` stamps it into `.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json`, and CI fails on drift. During active pre-1.0 development the
  plugin manifests intentionally carry **no `version`** (commit-SHA versioning); a `version` is added
  at the first tagged release. SemVer rules:
  - **MAJOR** — backwards-incompatible change to the public CLI surface, the normalized data model, or
    the on-disk JSON exports.
  - **MINOR** — backwards-compatible new subcommands, flags, checks, readers, or ops.
  - **PATCH** — backwards-compatible bug fixes and internal changes.

- **`schema_version`** (stamped on every `Schematic`/`Pcb`/`Library` JSON export; currently `"1.0"`).
  Bumped independently of the package version. A **minor** schema bump only adds optional fields
  (consumers must ignore unknown keys); a **major** schema bump may remove or rename fields and
  coincides with a package MAJOR bump.

- **`protocol_version`** (integer; currently `1`) governs the op-list document and the Windows live
  bridge. It is bumped **only** on a breaking change to op shapes, the result object, or the bridge
  handshake. Executors and the bridge **reject a higher major `protocol_version`** with
  `ERROR: PROTOCOL_MISMATCH` rather than guessing. Adding a new optional op or optional op field does
  **not** bump `protocol_version`.

When in doubt, prefer additive, backwards-compatible changes and leave the version contracts untouched.

## [Unreleased]

Not yet tagged or published to PyPI; install from source (see `INSTALL.md`).

### Added
- **Readers:** Altium `.SchDoc` / `.SchLib` and ASCII `.PcbDoc`; KiCad `.kicad_sch` (v7/v8) via a
  bounded, non-recursive S-expression parser with pin-type resolution from `lib_symbols`.
- **Net inference** (`netbuild`) shared across both formats: same-name merge, junctions/T-junctions,
  No-ERC handling.
- **CLI:** `read`, `net`, `component`, `check` (ERC/power/BOM), `diff` (net-membership), `pinmap`,
  `export`.
- **KiCad write/draw:** `plan` / `draw` from a versioned JSON op-list — atomic, idempotent (UUIDv5),
  connectivity-verified.
- **JLCPCB/LCSC parts:** `jlc search` / `show` / `add` (conversion via external `nlbn` / `npnp`).
- **Claude Code plugin:** circuit-design skill + `circuit-review` / `circuit-pinmap` / `circuit-draw` /
  `circuit-diff` commands; DTS / pinout adapters.
- **Altium live driver (preview):** Python file-based JSON bridge; the Windows DelphiScript half is a
  scaffold pending validation.
- Documentation (`README.md`, `INSTALL.md`, `SECURITY.md`, `THIRD_PARTY_NOTICES.md`, `docs/SPEC.md`,
  `docs/cli-reference.md`), reference config, and CI matrix.

### Fixed
- **Footprints** now fall back to the RECORD-41 `Footprint` / `Supplier Footprint` parameter when the
  RECORD-45/46 model link is empty (npnp-generated parts), removing false `BOM_MISSING_FOOTPRINT`.
- **Rail voltage inference** no longer mis-fires on underscore-suffixed rails (`V3V3_BNO`, `V3V3_FSR`):
  the trailing word-boundary that `_` defeated is replaced; logic is now shared in `checks/_rails.py`,
  and configured `[[rail]]` names match `<rail>_suffix` too. Fixes false `ERC_NO_POWER`.
- **`export --json`** now errors (exit 2) with guidance instead of emitting non-JSON at exit 0.
- **`.SchLib` / `.PcbDoc`** binary records now surface as `ALTIUM_UNSUPPORTED` (exit 5, *unsupported*)
  instead of `ALTIUM_MALFORMED` (exit 3, *parse error*).
- **`pinmap --expected`** unmatched pins are now `WARNING` (non-zero exit) instead of a silent NOTE.
- **`-C/--config`** (and other global flags) are accepted before *or* after the subcommand.
- Report JSON (`check`/`diff`/`pinmap`) now carries `schema_version`.
- GBK/cp936 fallback for `%UTF8%` values that aren't valid UTF-8 (Ω/µ/± from Chinese-locale tools).
- `tarfile` extraction uses `filter="data"` (Python 3.14-ready, hardened).

### Notes
- Baselines at the first tagged release: package `0.1.0`, `schema_version = "1.0"`,
  `protocol_version = 1`.

[Unreleased]: https://github.com/tipoLi5890/altium-kicad-cli/commits/main
