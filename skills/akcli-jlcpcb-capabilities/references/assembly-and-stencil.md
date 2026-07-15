# 嘉立創 (jlc.com) SMT assembly & laser stencil reference

Assembly (PCBA) placement limits and stencil (鋼網) specs for **嘉立創 domestic**.
Sources: 工藝能力頁 <https://www.jlc.com/portal/vtechnology.html> and
激光鋼網 <https://www.jlc.com/portal/smtLaserSteelNet.html>, 2026-07-06 /
re-verified 2026-07-15. **Assembly limits bite at schematic time** — they decide
which packages you may choose before any layout exists, so this is the table an
agent consults while sourcing parts.

---

## SMT assembly: 經濟型 (Economic) vs 標準型 (Standard)

| Item | 經濟型 Economic | 標準型 Standard |
|---|---|---|
| Sides | single (SMD + THT) | single / double |
| Layers / thickness | 2 / 4 / 6, 0.8–1.6 mm | unlimited |
| Board size | 10×10 – 470×570 mm | 70×70 – 460×510 mm |
| **Min passive package** | **0402** | **0201** |
| Min IC pitch | 0.4 mm | 0.35 mm |
| **Min BGA pitch** | 0.5 mm | **0.3 mm** |
| Reflow profile | 255 ± 5 °C, fixed | 240 ± 5 °C, adjustable |
| SPI / enhanced AOI | no | yes |
| Process border + Mark | not required | **required — 5 mm border + 1 mm Mark 光點** |

### How to use this while designing

- **Choose packages the line can place.** For Economic, that means ≥0402
  passives, IC pitch ≥0.4 mm, BGA ≥0.5 mm; Standard extends to 0201 / 0.35 mm IC
  / 0.3 mm BGA but adds SPI, AOI and the required process border.
- **Prefer Basic / Preferred parts** (fewer feeder-setup fees) — use
  `akcli jlc search` and the `akcli-parts-sourcing` skill.
- **Standard needs a 5 mm process border with a 1 mm Mark point** — budget it
  into the board outline / panel early, not after layout.
- **Double-sided assembly** and **fine-pitch/BGA** push you to Standard; note the
  service-line choice in the order.

---

## Design-for-assembly (DFA) — beyond package/pitch

Placement limits (above) decide *which* parts you may use; these decide whether
they **assemble cleanly**. The 5 mm process border + 1 mm Mark are JLC
Standard-line requirements (above); the rest is standard SMT-assembly practice
JLC follows — confirm specifics at order time.

- **Component-to-board-edge clearance:** keep parts (and their courtyards) off a
  bare board edge — conveyor rails and depaneling stress need room. With no
  process border, keep ~5 mm; the Standard-line 5 mm border provides it on a
  panel.
- **Pin-1 / polarity marking on silk (prevents the #1 PCBA defect):** put a pin-1
  dot / bevel / polarity mark on `F.Silkscreen` (or `B.`) for every polarized
  part — ICs, diodes, electrolytics/tantalums, connectors. It is what makes the
  CPL placement preview reviewable and stops reversed-part builds. KiCad
  footprints carry these — keep them un-suppressed and off pads (silk-on-pad is
  deleted; see `dfm-and-file-prep.md`).
- **Tombstoning (chip passives):** for 0402 / 0201, keep the two pads thermally
  symmetric — a pad tied straight into a large plane heats and wets unevenly and
  the part tombstones. Use thermal-relief spokes into planes (spoke ≥ hole Ø +
  0.5 mm) and match end-pad copper.
- **Courtyard / spacing:** honor footprint courtyards; crowding fine-pitch parts
  risks bridging and blocks rework. Tall parts / connectors near the edge or
  border can foul the conveyor.
- **THT (through-hole):** JLC assembles THT too, but it is hand / selective
  soldered — slower and a per-joint cost vs SMT reflow; prefer SMT where possible.
- **DNP / do-not-place:** mark DNP correctly so parts are excluded from the CPL —
  `kicad-cli pcb export pos --exclude-dnp` and `akcli jlc bom` handle it; a
  mis-marked DNP is either placed (waste) or omitted (missing part).

None of this is checked by `akcli fab check` (fab-policy/cost, not assembly DFA)
— it is human-review / footprint-hygiene territory. Gate polarity by eyeballing
the CPL placement preview before ordering.

---

## Laser stencil (SMT 激光鋼網)

| Item | Capability |
|---|---|
| Material / cutting | 304TA steel foil, LPKF laser, positional tol ±0.003 mm, min aperture >0.08 mm |
| Foil thickness | 0.06 / 0.08 / 0.10 / 0.12 / 0.13 / 0.15 / 0.18 / 0.20 / 0.30 mm (standard 0.10–0.20; special 0.03–0.06 and 0.25–0.5) |
| Sizes | 20+ standard (37×47, 42×52, 55×65, 73.6×73.6 cm …) |
| Polish | 電解拋光 (electropolish) / 打磨拋光 — **electropolish recommended for pitch ≤0.5 mm and BGA** |
| Lead time / formats | 6 hours – 2 days; accepts Gerber / Protel / PowerPCB |

**Rules of thumb:** 0.12 mm foil for a mixed 0402 + fine-pitch board;
electropolish whenever pitch ≤0.5 mm. The stencil aperture (paste layer) comes
from `F.Paste`/`B.Paste`, which is a separate layer from the solder mask — see
`dfm-and-file-prep.md`.

The international (jlcpcb.com) stencil service uses the same 304 steel / ±0.003 mm
/ >0.08 mm aperture family; frame/frameless size ranges differ — see
`jlcpcb-international.md`.
