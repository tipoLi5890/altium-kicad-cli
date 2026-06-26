# Installing altium-kicad-cli

`altium-kicad-cli` is a **zero-runtime-dependency** Python package. It needs only **Python ≥ 3.11**
(for the stdlib `tomllib` module). There is nothing to compile and no EDA software to install.

- PyPI distribution: `altium-kicad-cli`
- import package: `altium_kicad_cli`
- CLI command: `akcli` (long alias: `altium-kicad-cli`)
- Claude Code plugin / marketplace name: `altium-kicad`

> **Status:** pre-alpha. PyPI publishing is part of a later milestone — until the first release lands,
> install from a clone (Option B) or via `pipx install git+...` (Option C).

## Requirements

- **Python ≥ 3.11.** Check with `python3 --version`.
  - macOS ships an older `python3` (often 3.9) — install a newer one with `brew install python@3.12`
    or from [python.org](https://www.python.org/downloads/). The `bin/akcli` wrapper auto-discovers
    `python3.13`/`3.12`/`3.11` if your default `python3` is too old.
- No other runtime dependencies. (Development/testing extras are opt-in: see below.)

## Option A — pipx (recommended once published)

`pipx` installs the CLI into an isolated environment and puts `akcli` on your PATH.

```bash
pipx install altium-kicad-cli
akcli --version          # prints package + protocol version
akcli --help
```

Upgrade / uninstall:

```bash
pipx upgrade altium-kicad-cli
pipx uninstall altium-kicad-cli
```

## Option B — run from a clone (no install, zero deps)

Because there are no runtime dependencies, you can run straight from a checkout:

```bash
git clone https://github.com/tipoLi5890/altium-kicad-cli
cd altium-kicad-cli
./bin/akcli --help                  # self-locating wrapper; finds Python ≥ 3.11 for you
```

Add it to your PATH if you like:

```bash
export PATH="$PWD/bin:$PATH"        # exposes both `akcli` and `altium-kicad-cli`
```

Or invoke the module directly with any Python ≥ 3.11:

```bash
PYTHONPATH=src python3.12 -m altium_kicad_cli --help
```

## Option C — pip / from git

```bash
pip install altium-kicad-cli                                   # once on PyPI
pip install git+https://github.com/tipoLi5890/altium-kicad-cli # latest from main
```

A virtual environment is recommended to avoid touching system Python:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install altium-kicad-cli
```

## Claude Code plugin

The repository is also a Claude Code plugin (it ships a self-marketplace). Install it from inside
Claude Code:

```text
/plugin marketplace add tipoLi5890/altium-kicad-cli
/plugin install altium-kicad@altium-kicad
```

After install you get the circuit-design skill and the `/altium-kicad:circuit-review`,
`circuit-pinmap`, `circuit-draw`, and `circuit-diff` commands, all of which call `akcli`. The plugin
bundles `bin/akcli`, which selects a suitable Python interpreter automatically.

## Development install (tests / contributing)

Dev and test tools are an optional extra (`pytest`, `jsonschema`, `build`, `twine`); the runtime stays
dependency-free.

```bash
git clone https://github.com/tipoLi5890/altium-kicad-cli
cd altium-kicad-cli
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Build and validate the distribution locally:

```bash
python -m build
twine check dist/*
```

## Optional external tools

- **`kicad-cli` (KiCad 8.x):** enables an *optional secondary* ERC/netlist cross-check. `akcli` detects
  it via `PATH`; if it is absent, the pure-Python connectivity verifier is used and nothing breaks.
- **Altium Designer 22+ on Windows:** required only for the optional *live* write/draw driver. Offline,
  Altium files are read-only and need no Altium install.

## Verify your install

```bash
akcli --version          # package version + protocol_version
akcli read --help        # subcommand help
akcli --help             # list all subcommands
```

If `akcli` reports it cannot find Python ≥ 3.11, install a newer interpreter (see Requirements) and
re-run; the wrapper will pick it up. See [SECURITY.md](SECURITY.md) for the untrusted-input threat
model before pointing the tool at files from unknown sources.
