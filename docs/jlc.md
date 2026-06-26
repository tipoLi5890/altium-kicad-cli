# `akcli jlc` — JLCPCB / LCSC part search

Search the JLCPCB / LCSC component catalog from the command line. This is the
**only networked feature** in altium-kicad-cli; every other command is fully
offline and zero-dependency.

> **Needs network.** `jlc` calls the public **jlcsearch** service
> (`https://jlcsearch.tscircuit.com`). All other `akcli` commands work with no
> network and no Altium/KiCad install. Network code is import-isolated under
> `altium_kicad_cli.parts` and loaded lazily, so it never touches the offline paths.

## Commands

### `akcli jlc search <query> [--limit N] [--json]`

Keyword search. The query matches manufacturer part number (MPN), category, and
the LCSC C-number (with or without the `C` prefix).

```bash
akcli jlc search NE555
akcli jlc search NE555 --limit 5
akcli jlc search "0603 100nF" --json
```

Text output is a table (`LCSC  MPN  PACKAGE  STOCK  PRICE  B  DESCRIPTION`),
where the `B` column is `B` for a JLCPCB **Basic** part, `P` for a **Preferred**
part, else `-`. `--json` emits the full list of part objects.

Exit codes: `0` on results **and** on a clean no-results path (a `no parts found`
notice goes to stderr); `7` on a network/HTTP error (a single
`ERROR: NETWORK: …` line goes to stderr — never a traceback).

### `akcli jlc show <C-number> [--easyeda] [--json]`

Fetch one part by its LCSC C-number (e.g. `C7593` or bare `7593`).

```bash
akcli jlc show C7593
akcli jlc show C7593 --json
akcli jlc show C2040 --easyeda          # also: 3D-model availability + EasyEDA metadata
```

`--easyeda` adds a light, read-only metadata lookup against EasyEDA's **unofficial**
Std-editor backend to report whether a **3D/STEP model is available**, plus the
manufacturer/MPN/package EasyEDA has on file. It converts nothing. The lookup is
best-effort: if EasyEDA is unreachable or the endpoint changes, the EasyEDA section is
simply omitted (or shows `(metadata unavailable)`) — it never breaks `jlc show`.

Exit codes: `0` when found, `0` with a `no part … found` stderr notice when the
C-number does not exist, `7` on a network/HTTP error.

### `akcli jlc add <C-number> --to {kicad,altium} [...]`

Fetch a real LCSC/EasyEDA part **and convert it into a library** — a KiCad
symbol/footprint/3D set (`--to kicad`) or an Altium `.SchLib`/`.PcbLib` pair
(`--to altium`).

```bash
akcli jlc add C2040 --to kicad                       # symbol + footprint
akcli jlc add C2040 --to kicad --3d                  # + 3D STEP model
akcli jlc add C2040 --to kicad --out ./mylib --lib-name akcli
akcli jlc add C2040 --to altium                      # .SchLib + .PcbLib (Windows tool)
akcli jlc add C2040 --to kicad --place --designator U1 --at 1000 1500
```

| flag | meaning |
|---|---|
| `--to {kicad,altium}` | **required** — target library format |
| `--3d` | include the 3D STEP model (KiCad: `--full`; Altium: STEP embedded into the PcbLib) |
| `--out DIR` | output directory (default `./akcli-parts/<C-number>/`) |
| `--lib-name NAME` | KiCad library name (default `akcli`) |
| `--force` | overwrite existing artifacts |
| `--english` | pull English metadata |
| `--auto-download` | allow fetching the pinned, checksum-verified converter binary (default **off**) |
| `--place` | also emit a `place_component` op-list (KiCad only — see below) |
| `--designator REF` / `--at X Y` | required with `--place` (reference + position in mils) |

Exit codes: `0` on success; `2` on bad usage (missing `--to`, bad C-number, `--place`
without `--designator`/`--at`, or `--to altium --place`); `4` when the part is not found;
`6` when the converter ran but failed or produced nothing; `7` when the external binary
is absent (an install hint is printed) or an enabled download fails.

Every successful conversion prints a **verify caveat** — the symbol/footprint/3D are
produced by a third-party converter from EasyEDA/LCSC data and can be wrong (pin mapping,
courtyard, 3D origin). **Always verify against the datasheet**, and for KiCad run a
follow-up `akcli check` / `kicad-cli erc` pass before using the part.

#### `--place` (drop the fetched part into a schematic)

With `--place` (KiCad only) `jlc add` writes a one-op `place_component` op-list to
`<out>/place.json`. It does **not** mutate any schematic itself — placement stays an
explicit, reviewable second step through the op-list executor:

```bash
akcli jlc add C2040 --to kicad --out ./mylib --place --designator U1 --at 1000 1500
akcli draw board.kicad_sch --ops ./mylib/place.json --symbols ./mylib/akcli.kicad_sym --apply
```

The op's `lib_id` symbol name is read from the produced `.kicad_sym` (the converter names
parts by component name, not the C-number), and the `footprint` id from the produced
`.kicad_mod` — neither is guessed from a filename.

## External tools (`jlc add`) — used at arm's length

`jlc add` shells out to two **external Apache-2.0 Rust binaries** by **linkyourbin**:

- **`nlbn`** — LCSC/EasyEDA → KiCad (used by `--to kicad`).
  <https://github.com/linkyourbin/nlbn>
- **`npnp`** — LCSC/EasyEDA → Altium `.SchLib`/`.PcbLib` (used by `--to altium`).
  Ships **Windows-x86_64 only**; on macOS/Linux build it with
  `cargo install --git https://github.com/linkyourbin/npnp`.
  <https://github.com/linkyourbin/npnp>

These tools are **invoked as separate subprocesses only** — altium-kicad-cli never
imports, vendors, links, or copies source from them, and stays Python-stdlib-only with
zero runtime dependencies. Install a binary on your `PATH` (`cargo install nlbn`, or
download a pinned release), or re-run with `--auto-download` to let altium-kicad-cli
fetch the **version-pinned, SHA-256-verified** prebuilt release into its cache (off by
default; enabling it means trusting that specific pinned `linkyourbin` release). When no
binary can be resolved, `jlc add` prints a copy-pasteable install hint and exits `7` — it
never auto-downloads silently.

## Part fields (JSON)

| field | meaning |
|---|---|
| `lcsc` | LCSC C-number, e.g. `C7593` |
| `mpn` | manufacturer part number |
| `description` | catalog description (often empty in jlcsearch) |
| `package` | package / footprint name, e.g. `SOIC-8`, `0603` |
| `stock` | JLCPCB stock quantity |
| `price` | representative unit price (lowest-quantity tier) as a float, or `null` |
| `basic` | `true` for a JLCPCB Basic part |
| `datasheet` | datasheet URL when provided, else `null` |
| `category` | top-level category |
| `attributes` | extra fields: `subcategory`, `is_preferred`, `price_tiers`, `specs` |

The upstream `price` is a tiered structure; `attributes.price_tiers` keeps the
full `[{qFrom, qTo, price}, …]` ladder while `price` surfaces the cheapest
single-unit (lowest-`qFrom`) tier for quick comparison.

## Library use

```python
from altium_kicad_cli.parts import search as jlc

parts = jlc.search("NE555", limit=10)        # list[Part]
part  = jlc.get("C7593")                      # Part | None

# inject a transport (any urllib OpenerDirector-like object) to run offline/test:
parts = jlc.search("NE555", opener=my_fake_opener)

# optional short on-disk cache keyed by request URL, to avoid hammering the API:
parts = jlc.search("NE555", cache_dir="/tmp/akcli-cache", cache_ttl=3600)
```

Network failures raise `altium_kicad_cli.parts.search.JlcNetworkError` (clean
message, no traceback).

## Attribution

Part data comes from **jlcsearch** by tscircuit
(<https://github.com/tscircuit/jlcsearch>, MIT licensed), a search front end over
the JLCPCB / LCSC catalog built on the **jlcparts** dataset
(<https://github.com/yaqwsx/jlcparts>, MIT). altium-kicad-cli is an independent
client of the public service and is not affiliated with JLCPCB, LCSC, tscircuit,
or jlcparts. Please use the service respectfully (low request volume; the
optional on-disk cache helps).
