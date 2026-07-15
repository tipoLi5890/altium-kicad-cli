# JLCPCB international (jlcpcb.com) — difference reference

嘉立創 (jlc.com, domestic CN) and **JLCPCB (jlcpcb.com, international)** are the
**same company but different service lines with different limits**. Read this
file when the user will actually order on jlcpcb.com. Sources:
<https://jlcpcb.com/capabilities/pcb-capabilities>, `flex-pcb-capabilities`,
`pcb-assembly-capabilities`, `pcb-stencil-manufacturing` (2026-07-06 /
re-verified 2026-07-15).

**The international line mostly matches 嘉立創 at 1–2 oz mainstream specs** (same
0.10/0.09 mm trace, 0.15/0.25 mm via, mask dams, silkscreen, V-cut / mouse-bite
numbers) — so the `rigid-pcb.md` mainstream tables apply. The differences below
are the **tighter international limits**; when any of these is in play, use the
international number, not the domestic one.

---

## Headline differences (domestic → international)

| Item | 嘉立創 jlc.com | JLCPCB intl |
|---|---|---|
| Max layers | **64** | **32** |
| Blind/buried vias (HDI) | supported (4–32 L HDI) | **not supported** |
| Microvia | 0.1 mm (2–12 L, ≤1 mm, 沉金) | **0.15 mm min** |
| Outer copper (2-layer) | up to **6 oz** | up to **4.5 oz** |
| Board thickness | 0.4–**4.8 mm** | 0.4–**4.5 mm** |
| Multilayer PTH annular | 0.20 rec / 0.15 limit | **0.25 rec / 0.18 limit** |
| Standard-assembly min BGA pitch | 0.3 mm | **0.35 mm** |
| Press-fit holes | 0.55–**2.0 mm** | 0.55–**1.025 mm** |
| Castellated (half-hole) | ≥0.5 mm | ≥0.5 mm |
| Board↔board panel gap | — | ≥2 mm |
| Circular boards | — | ≥20×20 mm |

## Assembly quantities

- **Economic assembly:** 2–50 pcs.
- **Standard assembly:** 2–80,000 pcs.

## Blockers to surface early

- **No blind/buried vias or 0.1 mm microvia internationally.** If the design's
  HDI/microvia is essential, either the design must change or the order must go
  to the domestic line — flag this the moment HDI appears.
- **32-layer ceiling** and **4.5 oz / 4.5 mm** caps — a domestic-designed 40-layer
  or 6 oz board cannot be built internationally.

## International stencil

Same 304 steel / ±0.003 mm positional tol / >0.08 mm min aperture family as
domestic. Size ranges:

- **Frameless:** 280×380 – 700×600 mm.
- **Framework:** 400×300 (valid area 240×140) – 736×736 (valid 500×500); rect
  frames up to 1500×500 mm.
- **Foil:** standard 0.10–0.20 mm (special 0.03–0.08 and 0.25–0.5 mm, upcharge).
- **Fiducials:** none / through / half-etched.
- **Step stencils:** framework only. Top / bottom / combined available.

Rule of thumb unchanged: 0.12 mm foil for mixed 0402 + fine-pitch; electropolish
for pitch ≤0.5 mm.
