# 嘉立創 (jlc.com) rigid PCB capability reference

Full manufacturing limits for **嘉立創 domestic (jlc.com)** rigid boards (FR-4
unless noted). Source: 工藝能力頁 <https://www.jlc.com/portal/vtechnology.html>,
extracted 2026-07-06, re-verified 2026-07-15. **Ordering internationally
(jlcpcb.com) is a different, generally tighter service line — see
`jlcpcb-international.md`.**

Two number types appear throughout: **建議值 (recommended)** — safe, no upcharge,
what a design should target — and **極限值 (absolute limit)** — the factory can
do it, often at a price class change and 沉金 (ENIG) requirement. When you quote a
limit, say it is a limit, not a target.

---

## 1. Layers, size, thickness, materials

| Item | Capability | Notes |
|---|---|---|
| Layers | **1–64** | HDI (blind/buried) needs 4+ layers; see §4 |
| Max size | 1L 606×510 · 2L 670×600 · 4L 663×593 · 6–64L 656×586 mm | larger boards → panelize |
| Min size | 3×3 mm (FR-4 / high-freq) · 5×5 mm (Al / Cu core) | below → add a routed border and panelize |
| Thickness | **0.4–4.8 mm** | tol ±10 % for ≥1.0 mm, ±0.1 mm for <1.0 mm |
| Materials | FR-4 Grade A, HDI, high-frequency (Rogers/PTFE), aluminum, copper core | metal-core changes many rules (see slot/finish limits) |

Standard core suppliers are 南亞 / 建滔 KB / 生益 with ≥99.9 % electrolytic
copper; call out a specific laminate (Tg, Dk/Df, controlled dielectric) in the
order notes when it matters.

---

## 2. Copper weight (finished)

| Position | Options |
|---|---|
| Outer, 2-layer | 1 / 2 / 2.5 / 3.5 / 4.5 / 5 / **6 oz** |
| Outer, multilayer | 1 / 2 oz |
| Inner | 0.5 / 1 / 2 oz |

Copper weight is the single biggest rewrite of the trace/space and mask-dam
rules (§3, §6) — **re-check every clearance whenever the user asks for heavy
copper.** 1 oz is the free default; ≥2 oz is a cost/upcharge decision.

---

## 3. Trace width / spacing (minimum, by finished copper)

Width tolerance is **±20 %**. Single/double-sided boards etch slightly finer
than multilayer (inner layers are harder to control).

| Copper | 單/雙面 (single/double) | 多層 (multilayer) |
|---|---|---|
| **1 oz** | 0.10 / 0.10 mm (4 / 4 mil) | 0.09 / 0.09 mm (3.5 / 3.5 mil) |
| 2 oz | 0.16 / 0.16 mm (6.5 mil) | 0.15 / 0.15 mm (6 mil) |
| 2.5 oz | 0.20 / 0.20 mm (8 mil) | — |
| 3.5 oz | 0.25 / 0.25 mm (10 mil) | — |
| 4.5 oz | 0.30 / 0.30 mm (12 mil) | — |
| 5 oz | 0.35 / 0.35 mm (14 mil) | — |
| 6 oz | 0.45 / 0.45 mm (18 mil) | — |

- **Comfortable default (1 oz):** design at ≥0.127 mm (5 mil) trace/space —
  well clear of the 0.09/0.10 mm limit at zero cost. Only push to the limit for
  dense BGA fan-out, and label it a limit.
- **Grid/mesh copper:** keep mesh line width and spacing ≥0.25 mm.
- **KiCad mapping:** set the board's net-class clearance/track-width to the
  chosen copper's value; `akcli fab check --profile` gates the finished board
  against a versioned copy of these numbers.

---

## 4. Vias, drills, HDI

Ordinary through-hole via default: **0.3 mm hole / 0.6 mm pad** — comfortable,
free. The limit numbers below are for dense designs and come with cost / ENIG
strings attached.

| Item | Capability |
|---|---|
| Mechanical drill | 0.15–6.3 mm (2+ layers) · 0.3–6.3 mm (1 layer) · Al ≥0.65 · Cu core ≥1.0 |
| **Min via** (double/multi) | **0.15 mm hole / 0.25 mm pad** — pad ≥ hole + 0.1 (rec + 0.15); via↔via edge ≥0.2 mm |
| Min via (single-layer) | 0.3 mm hole / 0.5 mm pad |
| **Microvia 微孔** | **0.1 mm** — 2–12 layers, board ≤1 mm, 沉金 only, pad ≤0.2 mm |
| **Blind via (laser) 盲孔** | 0.075–0.15 mm, electrolytic-filled |
| **Buried via (mech) 埋孔** | 0.10–0.55 mm, resin / copper-paste fill + cap |
| HDI stack | 4–32 layers |
| Backdrill 背鑽 | 4–64 L, board ≥0.8 mm; hole 0.2–0.5 mm (resin-filled); backdrill Ø = hole + 0.2; dielectric ≥0.15 mm |
| Blind slot 盲槽 | width ≥1.0, depth ≥0.2, ring ≥0.3 (PTH) / 0.2 (NPTH); board ≥0.8 mm |
| Via fill 塞孔 | 油墨塞孔 0.15–0.5 · 樹脂塞孔+電鍍蓋帽 0.15–0.55 (default on 6+ L) · 銅漿塞孔+蓋帽 0.15–0.55 (thermal) |
| Hole tolerance | 插件孔 (PTH) +0.13 / −0.08 mm · 壓接孔 (press-fit) ±0.05 mm (0.55–2.0 mm, multilayer 沉金 only) |

**Via fill ≠ via covering.** The *Via fill* row above fills the **barrel** (a fab
process). Whether the solder mask **covers** the via on the surface — tented
(free, default) / untented / paid resin-or-copper fill+cap for via-in-pad — is a
separate **order option with cost consequences**, and it is what `akcli fab check`
reasons about. See `cost-and-fab-profile.md` §1.

### Annular ring (孔環)

| Case | Recommended | Limit |
|---|---|---|
| Double-sided PTH | ≥0.25 mm | 0.18 mm |
| **Multilayer PTH** | ≥0.20 mm | **0.15 mm** |
| Unplugged via, double-layer (NPTH-like) | ≥0.45 mm | — (dry-film recesses the pad ~0.2 mm) |

- **Blind/buried vias only exist on 嘉立創** — if the design needs them and the
  user might order internationally, surface that as a **blocker early**.
- Microvia / blind-via / via-fill / backdrill are all **price-class changers**
  and usually require 沉金.

### Half-hole (castellated 半孔) & slots

| Item | Capability |
|---|---|
| Half-hole | ≥0.5 mm dia · ≥1 mm to board edge · ≥0.5 mm pitch · board ≥10×10 mm, ≥0.6 mm thick |
| Plated slot | 雙面 ≥0.5 mm / 多層 ≥0.35 mm wide; length ≥2× width (min 1.0 / 0.7 mm) |
| Non-plated slot | ≥1.0 mm wide |
| Al / Cu-core slot | ≥1.6 mm wide |
| Pad↔track | ≥0.1 mm @1 oz (BGA 0.09 mm); pad-hole↔pad-hole ≥0.45 mm |
| BGA pad | ≥0.2 mm (≤0.25 mm pad ⇒ 沉金 only); ↔track ≥0.1 mm (0.09 mm multilayer) |

---

## 5. Solder mask (阻焊) & silkscreen (字符)

| Item | Capability |
|---|---|
| Mask colors | 綠 / 紫 / 紅 / 黃 / 藍 / 白 / 黑 (感光油墨), thickness ≥10 µm |
| **Opening** | **1:1 with the pad since 2025-06 (LDI equipment upgrade)** — design ≥0.02 mm, engineering adjusts |
| **Mask dam (阻焊橋)** | 1 oz: ≥0.10 mm (綠紅黃藍紫) / **≥0.13 mm (黑白, coarser)**; 2 oz: ≥0.20 mm |
| Mask↔trace | ≥0.09 mm |
| Silkscreen | height ≥1 mm (CJK often needs more), stroke ≥0.15 mm, ≥0.15 mm off any copper/pad; **no text on a pad** (JLC removes it) — see `dfm-and-file-prep.md` |

Black and white masks are **coarser** (0.13 vs 0.10 mm dam @1 oz) — if a dense
board needs tight dams between fine-pitch pads, prefer green.

---

## 6. Board outline, panelization, finishes

| Item | Capability |
|---|---|
| Routed edge 鑼邊 | copper↔edge ≥0.2 mm; tol ±0.2 mm (precision ±0.1 mm needs board ≥50×50 mm + 3 tooling holes ≥1.5 mm) |
| **V-cut V割** | copper↔edge ≥0.4 mm; tol ±0.4 mm (board ≥0.6 mm); panel 70–475 mm; cut pitch ≥3 mm (extreme 2 mm); default 0 mm gap |
| Mouse-bite 郵票孔 | gap 1.6–2 mm; process border ≥3 mm — **JLC SMT assembly wants 5 mm border + 1 mm Mark 光點** |
| Impedance control | multilayer only, ±10 % (upcharge); design with JLC's 阻抗計算神器; **must be declared in the order — not auto-detected from files** |
| Surface finishes | 有鉛噴錫 / 無鉛噴錫 / 沉金 (ENIG) / OSP |

**Finish constraint matrix:** aluminum substrate = 噴錫 only; ≤0.4 mm boards,
high-frequency, copper-base and FPC cannot 噴錫; aluminum / copper-base / FPC
cannot use 有鉛 (leaded). Pick 沉金 for fine-pitch/BGA and for the extreme via/pad
values above.

---

## Quick "is it free?" heuristic

A 1 oz, 2–4 layer FR-4 board at ≥5 mil trace/space, 0.3/0.6 mm vias, green mask,
沉金 or HASL, no blind/buried vias, board ≥ min size, standard thickness — sits
comfortably inside every limit at the base price class. Anything that touches
**heavy copper, HDI/microvia, via-fill, backdrill, 6+ layers, impedance
control, or a limit-value trace/via** moves the price class and often forces
沉金. Gate the actual board with `akcli fab check --profile` rather than eyeballing.
