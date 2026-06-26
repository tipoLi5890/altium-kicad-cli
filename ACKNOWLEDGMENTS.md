# Acknowledgments

`altium-kicad-cli` stands on the work of several open-source projects and a public data
source. We use them **at arm's length**: external tools are invoked as **subprocesses**, and
public services are queried over HTTP. **No third-party source code is imported, linked, or
vendored** into this package (it remains Python-standard-library-only with zero runtime
dependencies). Where a project's *patterns* informed our design, that is recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Fetch + convert tools (invoked as subprocesses)

- **nlbn** — LCSC/EasyEDA → KiCad symbol/footprint/3D exporter, by **linkyourbin**.
  Apache-2.0. <https://github.com/linkyourbin/nlbn>. `akcli jlc add --to kicad` shells out
  to the `nlbn` binary; we do not bundle or modify it.
- **npnp** (Normalize Pin Net Pad) — LCSC/EasyEDA → Altium `.SchLib`/`.PcbLib` exporter,
  by **linkyourbin**. Apache-2.0. <https://github.com/linkyourbin/npnp>. `akcli jlc add
  --to altium` shells out to the `npnp` binary; we do not bundle or modify it.

  Because nlbn and npnp are **Apache-2.0**, automating them via subprocess and optionally
  redistributing their prebuilt binaries is permitted with attribution — this is what
  removed the earlier AGPL concern around an easyeda2kicad-style converter.

## Search + parts data

- **jlcsearch** (tscircuit) — MIT — public search front end over the JLCPCB/LCSC catalog;
  used by `akcli jlc search` / `jlc show`. <https://jlcsearch.tscircuit.com>,
  <https://github.com/tscircuit/jlcsearch>.
- **jlcparts** — MIT — the open dataset/tooling behind that catalog data.
  <https://github.com/yaqwsx/jlcparts>.

## Data source

- **EasyEDA / LCSC / JLCPCB** — the underlying component, symbol, footprint, and 3D-model
  data. `akcli jlc show` performs a light, read-only metadata lookup against EasyEDA's
  **unofficial** Std-editor backend; the actual symbol/footprint/3D conversion is delegated
  to nlbn/npnp. EasyEDA, LCSC, and JLCPCB are trademarks of their respective owners; this
  project is not affiliated with or endorsed by them, and these endpoints are undocumented
  and may change without notice.

## Design-pattern reference

- **flaco-source / altium-mcp** (2026) and the earlier **coffeenmusic** / **Siddharth
  Ahuja** (2025) Altium-MCP lineage — referenced as an **independent-design pattern source
  only** (file-based JSON bridge, `protocol_version` handshake, structured `ERROR: CODE`
  strings) for the optional Windows live driver. No source was copied; full attribution is in
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Boundary statement

All of the above are used **without importing or vendoring their source**: nlbn/npnp run as
**separate processes**; jlcsearch/EasyEDA are **HTTP services**. `altium-kicad-cli` itself is
MIT-licensed and ships no third-party code.
