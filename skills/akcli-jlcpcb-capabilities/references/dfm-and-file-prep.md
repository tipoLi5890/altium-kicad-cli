# 嘉立創 (jlc.com) DFM & file-preparation reference

How to prepare a **manufacturable, correctly-ordered** design — the file-format
rules, the layer-mapping rules, and the "常見錯誤" (common mistakes) JLC's own
出圖指導 warns about. Source: <https://www.jlc.com/portal/server_guide_112.html>
(2026-07-15). The guide is written for Altium / PADS / Protel; the KiCad
equivalents are called out below. Capability *numbers* live in `rigid-pcb.md` /
`flex-fpc.md` — this file is about **file preparation and the mistakes that scrap
a first batch.**

---

## 1. File format & required outputs

- **Gerber must be RS-274-X.** JLC domestic explicitly **rejects Gerber X2 and
  RS-274-D**. KiCad's default Gerber output is RS-274-X, so `kicad-cli pcb export
  gerbers` is fine — just don't turn on X2 attributes. (Native Altium / PADS /
  Protel files are also accepted, but converting to RS-274-X avoids
  software-compatibility surprises.)
- **Drill file:** Excellon (`.txt` / `.xln`). `kicad-cli pcb export drill
  --format excellon` produces it.
- **A 2-layer board must ship:** top/bottom copper (GTL/GBL), top/bottom solder
  mask (GTS/GBS), top/bottom silkscreen (GTO/GBO), the **board outline** (GKO /
  GML), and the drill file. A 4-layer board adds the inner copper layers
  (L2/L3). The `kicad-cli` layer list in `SKILL.md` covers all of these.

## 2. Board outline & slots

- **Outline (and any slot) must live on one designated mechanical layer, drawn
  as real geometry.** In KiCad that layer is **`Edge.Cuts`** — it already is the
  single outline layer JLC wants, so KiCad users avoid the Altium/Protel
  "which mechanical layer / uncheck Keepout" confusion entirely.
- **A slot must be actual `Edge.Cuts` arcs/lines or an NPTH pad** — a 3D "board
  cutout" body is a *3D reference only* and does **not** export as a routed slot.
- Slot geometry: plated slot ≥0.5 mm wide (aspect length ÷ width ≥2:1);
  non-plated slot ≥1.0 mm wide (routed → rounded inner corners are unavoidable);
  keep ≥0.2 mm off any trace/pad. (Details in `rigid-pcb.md`.)

## 3. Solder mask vs paste — two different layers

- **Mask openings come from the solder-mask layer (`F.Mask`/`B.Mask`), NOT the
  paste layer.** "阻焊開窗以 Solder 層為準" — the paste layer (`F.Paste`/`B.Paste`)
  is the **stencil aperture only** and is not used to manufacture the board.
- Exposed copper with no mask layer = the factory has no window definition.
  Always output the mask layers separately from paste (the `kicad-cli` export
  already keeps them distinct).
- Via mask options: open window, mask bridge (阻焊橋), resin-fill, or
  copper-paste-fill. A double-sided open-window via cannot also be solder-mask
  plugged.

## 4. Silkscreen (字符)

- **No text on a pad.** "字符不允許上焊盤" — silkscreen overlapping a pad is
  **removed** by the factory, so a reference designator drawn across a pad simply
  vanishes.
- Standard font: stroke ≥0.15 mm, height ≥1 mm. High-precision: 0.1 mm stroke,
  0.8 mm height. Hollow characters: 0.2 mm stroke, 1.5 mm height. Keep ≥0.15 mm
  from any pad and ≥0.15 mm text-to-text.
- **Never hand-mirror bottom-side text** — KiCad (like the source tools) mirrors
  `B.Silkscreen` automatically; flipping it yourself double-mirrors it.

## 5. Plated vs non-plated (the silent-open trap)

This is the highest-consequence file-prep error:

- A hole mis-marked **non-plated (NPTH)** when it should be plated → **open
  circuit** (no barrel).
- A **through-hole pad mis-marked as a via** → the via loses its solder-mask
  opening → the pin **cannot be soldered**.
- The factory removes ~0.2 mm of copper around every NPTH for the dry-film
  process, which is why the unplugged-via annular ring is a large ≥0.45 mm
  (see `rigid-pcb.md` §4).

**Verify PTH vs NPTH on every hole before export** (in KiCad, the pad's plated
flag / hole type).

## 6. Thermal reliefs

- Spoke width ≥ hole Ø + 0.5 mm, and **stagger the spokes** — aligned spokes on a
  plane can bridge into a short.

## 7. Declare special intent — the files don't carry it

Some order-critical facts are **not detectable from the Gerbers** and must be
stated explicitly:

- **Controlled impedance** is not auto-detected — declare the target Ω, the
  reference plane, and the trace geometry in the order notes (and use JLC's
  阻抗計算神器).
- **A multi-design panel** needs its **exact design count** stated. A mismatch
  builds the wrong layout with **no refund**.
- These map directly onto akcli's **order manifest**: put them in `order.toml`
  (`design_count`, `delivery_format`, impedance/finish in notes) and gate with
  `akcli fab check --order`, which flags a missing or inconsistent declaration.

## 8. EDA-tool export notes

- **KiCad (this repo's target):** the `kicad-cli` block in `SKILL.md` produces
  RS-274-X Gerbers with the right layer set, an Excellon drill file, and a CPL
  from `akcli jlc bom` — no manual layer-mapping needed. Outline on `Edge.Cuts`,
  mask on `*.Mask`, paste on `*.Paste`.
- **Altium Designer 17+:** draw outline/slots on **Mechanical Layer 1**, avoid
  the **Keepout** layer (legacy AD/Protel exports drop slots that sit on Keepout
  when the "uncheck Keepout" box is enabled).
- **PADS:** use the **Hatch (refill)** copper mode before export to verify the
  pour — the **Flood** command edits the design and is risky; re-open the file
  after a pour to confirm no shorts.

---

## The nine mistakes JLC flags (checklist)

1. **Plated ↔ non-plated confusion** → open circuits.
2. **Through-hole pad output as a via** → loses its mask opening, unsolderable.
3. **Slots left on a Keepout layer** (legacy AD/Protel) → omitted from output.
4. **Slots on the wrong layer** (not the outline/mechanical layer) → missing.
5. **PADS Flood vs Hatch** → Flood mutates the design; use Hatch for verification.
6. **2D lines used as routing** → produce missing traces; route with the tool.
7. **Solder mask without a Solder layer** → exposed copper, no window defined.
8. **Bottom silkscreen hand-mirrored** → double-mirrored, backwards.
9. **Copper-pour not re-verified (PADS)** → hidden shorts; the factory applies
   Hatch only.

**First batch is customer-verified — JLC does not refund artwork errors on a
sample run.** So gate every board with `kicad-cli pcb drc` + `akcli fab check`,
and eyeball the placement / solder-mask preview before ordering.
