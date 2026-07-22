# Real-board corpus

Boards with a committed `<name>.ops.json` (`analog_frontend`, `power_entry`)
are **authored by akcli itself** — drawn by applying that op-list to a blank
`akcli new` sheet with the fixture symbol libraries
(`tests/fixtures/kicad/symbols/`), and re-derived in CI
(`test_corpus_board_reproducible`):

```bash  # doc-noqa
akcli new <name>.kicad_sch
akcli draw <name>.kicad_sch --ops <name>.ops.json \
  --symbols tests/fixtures/kicad/symbols/Device.kicad_sym \
  --symbols tests/fixtures/kicad/symbols/power.kicad_sym --apply --strict-nets
```

The boards deliberately keep their *honest* findings (missing footprints,
off-board nets) — the golden corpus (`tests/golden/`) freezes those outputs, so
a check/review/netlist behavior drift on realistic multi-block circuitry fails CI.

- `analog_frontend` — power entry π-filter (L1/C1/C2), 2× decoupling, I²C
  pull-up pair, reference divider, sensor divider + RC anti-alias filter;
  8 named nets, 13 components, exercises 5 macro ops.
- `power_entry` — power-protection calibration pair: a PROTECTED battery
  entry (VBAT → 500 mA fuse → series diode → VSYS bulk + decoupling) next to
  a deliberately UNPROTECTED VBUS sense branch (decouple, divider, RC — no
  fuse, no reverse element); 7 named nets, 9 components. The
  `signal.power_protect` review rules must stay silent on the first chain
  and fire exactly once each on the second.
- `groups_board` — a real 88-part / 89-net / 10-group production board,
  **committed directly** (no `.ops.json`, not re-derivable): it is the
  ground truth the 0.13.0 group repair loop was proven on
  (`tests/test_corpus_groups.py` pins its census, the net-preservation
  refusal, and the propose-labels → re-pack recovery).
