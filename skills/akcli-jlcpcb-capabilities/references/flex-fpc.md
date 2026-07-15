# 嘉立創 (jlc.com) FPC (flex) capability reference

Manufacturing limits for **嘉立創 domestic flexible PCBs**. Source: 工藝能力頁
<https://www.jlc.com/portal/vtechnology.html>, extracted 2026-07-06, re-verified
2026-07-15. FPC rules differ substantially from rigid — do **not** carry rigid
numbers over.

Key structural facts: 1 / 2 / 4 layers (**no rigid-flex yet**); electrolytic
(壓延) or rolled-annealed copper; the base film (PI/PET) and the coverlay
(instead of solder mask) define most of the special rules.

---

## Stackup, size, thickness, copper

| Item | Capability |
|---|---|
| Layers | 1 / 2 / 4 (no rigid-flex) |
| Base film (stackup) | PI 25 µm (standard) · PI 50 µm (超厚, thick) · PET 36 µm (透明, transparent) |
| Copper | 1L: 0.5 / 1 oz · 2–4L: 0.33 / 0.5 / 1 oz (electrolytic or rolled) |
| Size | ≤234×490 mm (extreme 250×600 mm with border); panelize anything <20×20 mm |
| Finished thickness | 1L 0.07 or 0.11–0.12 mm · 2L 0.11–0.24 mm · 4L per stackup |
| Stiffener (補強) tolerance | ±0.05 mm (≤0.3 mm) · ±0.1 mm (0.3–1.0 mm) · ±10 % (thicker); gold-finger zone ±0.03 mm |

Rolled-annealed copper survives dynamic flexing (repeated bends) far better than
electrolytic — call it out when the flex is a moving hinge, not a static fold.

---

## Trace / space (by copper)

Tolerance ±20 %. FPC etches **finer than rigid** at comparable weights.

| Copper | Trace / space | Extreme |
|---|---|---|
| 0.33 oz | 3 / 3 mil | 2 / 2 mil |
| 0.5 oz | 3.5 / 3.5 mil | — |
| 1 oz | 4 / 4 mil | — |

---

## Vias, drills, half-holes

| Item | Capability |
|---|---|
| Drill | 0.1–6.5 mm (PTH ≤5 mm recommended); tol ±0.08 mm |
| Via (standard) | 0.3 mm hole / 0.55 mm pad |
| Via (extreme, upcharge) | 2L 0.10 / 0.30 · 4L 0.15 / 0.35 mm; pad ≥ hole + 0.2 (rec + 0.25) |
| Annular ring | ≥0.25 mm recommended (0.18 mm limit); NPTH↔copper ≥0.2 mm |
| Plated slot | ≥0.5 mm |
| Half-hole | ≥0.3 mm dia · ≥0.5 mm to edge · ≥0.4 mm pitch |

---

## Coverlay, stiffeners, EMI, adhesives

| Item | Capability |
|---|---|
| Coverlay colors | 黃 / 黑 / 白 / 透明 |
| Coverlay opening | ≥ pad + 0.1 mm per side; ↔trace ≥0.15 mm; bridge ≥0.5 mm (else auto-opened); white adds +13–18 µm/side |
| Stiffener (補強) materials | PI 0.1–0.25 mm · FR-4 0.1–1.6 mm · 鋼片 (steel) 0.1–0.3 mm — **keep steel away from Hall sensors** |
| Stiffener adhesive | 3M 9077 0.05 mm · 3M 468 0.13 mm · Tesa 8854 0.1 mm (recommended) |
| EMI shielding film | 18 µm black; optional ground-window |

---

## Outline & panelization

| Item | Capability |
|---|---|
| Outline method | laser or punch; copper↔edge ≥0.3 mm; tol ±0.1 mm (±0.05 mm special); gold-finger↔edge 0.2 mm |
| Panel gap | 2 mm (3 mm if a steel stiffener is present) |
| Process border | 5 mm |
| Mark 光點 | 4× 1 mm — one offset ≥5 mm as an anti-reverse key |
| Tooling holes | 4× 2 mm |
| Breakaway tabs | 0.7–1.0 mm |

**Design-time takeaways:** budget the 5 mm process border and 4× fiducials into
the outline early; choose rolled copper for dynamic bends; keep coverlay
openings ≥ pad + 0.1 mm/side; and never place a steel stiffener over a magnetic
sensor. For any static-vs-dynamic bend-radius question, put it in the order
notes — it is a process choice, not a file attribute.
