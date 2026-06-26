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

Pre-alpha. The repository contains the frozen implementation specification (`docs/SPEC.md`) and is being
built milestone by milestone (see the Roadmap/Status table in `README.md`). No release has been tagged
or published to PyPI yet.

### Added
- Frozen hardened implementation SPEC (`docs/SPEC.md`).
- Project documentation and SEO assets: `README.md`, `INSTALL.md`, `SECURITY.md`,
  `THIRD_PARTY_NOTICES.md`, `LICENSE`, `docs/seo.md`, `docs/cli-reference.md`.
- Reference config `examples/altium-kicad-cli.toml.example`.
- SEO activation script `tools/seo-apply.sh` and CI workflow `.github/workflows/ci.yml`.

### Notes
- Initial baselines on first tagged release: package `0.1.0`, `schema_version = "1.0"`,
  `protocol_version = 1`.

[Unreleased]: https://github.com/tipoLi5890/altium-kicad-cli/commits/main
