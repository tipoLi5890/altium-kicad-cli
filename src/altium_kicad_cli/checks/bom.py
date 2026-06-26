"""BOM hygiene checks (SPEC §3.6).

``run(sch)`` inspects only the *component* layer of a :class:`model.Schematic`
(no net inference needed) and reports four classes of issue:

* **duplicate designator** -- two or more genuinely distinct components share a
  refdes. Multi-unit parts (several placements of one physical component sharing
  a ``UniqueId``) are *deduped*, not flagged.
* **refdes gap** -- a hole in a numeric-suffixed refdes sequence (e.g. ``R7`` and
  ``R12`` present but ``R8..R11`` missing). Gap detection runs **only within a
  numeric-suffixed prefix**: compound / manually-named refs such as ``J_USB_C``
  do not parse to ``(prefix, int)`` and are skipped, and a lone member (``X3``
  with no ``X1``/``X2``) has an empty min..max range so it never reports a gap.
* **missing value** / **missing footprint** -- a component with no value or no
  footprint string.

Synthesized (undesignated, ``$U<idx>``) components carry no real refdes and are
excluded from every BOM check; their count is already surfaced in the schematic
metadata header so the report is never vacuously clean.
"""

from __future__ import annotations

import re

from ..model import Component, Schematic
from ..report import Finding, Severity

__all__ = ["run"]

# A "simple" / numeric-suffixed refdes: one or more letters then digits, nothing
# else (``R12`` -> ("R", 12), ``U3`` -> ("U", 3)). Compound refs like ``J_USB_C``
# (an underscore-bearing manual name) do NOT match and are skipped from gaps.
_REFDES_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def _parse_refdes(ref: str) -> tuple[str, int] | None:
    """Split a refdes into ``(alpha-prefix, int-suffix)`` or ``None`` if compound."""
    m = _REFDES_RE.match(ref.strip())
    if not m:
        return None
    return m.group(1), int(m.group(2))


def _clean(s: str | None) -> str | None:
    """Normalize a value/footprint string: blank/whitespace -> ``None``."""
    if s is None:
        return None
    s = s.strip()
    return s or None


def _identity(comp: Component) -> object:
    """A dedup key: the ``UniqueId`` if present, else a per-object distinct key.

    Components sharing a non-empty ``UniqueId`` are units of one physical part
    (deduped); a missing id makes each placement its own identity so genuine
    duplicate refdes are still caught.
    """
    uid = _clean(comp.unique_id)
    return uid if uid is not None else ("__no_uid__", id(comp))


def _real_components(sch: Schematic) -> list[Component]:
    """Components eligible for BOM checks (drop synthesized/undesignated ones)."""
    return [c for c in sch.components if not c.undesignated and _clean(c.designator)]


def run(sch: Schematic) -> list[Finding]:
    """Run BOM hygiene checks on ``sch`` and return findings (possibly empty)."""
    findings: list[Finding] = []
    comps = _real_components(sch)

    # Group by designator, preserving first-seen order of the designators.
    groups: dict[str, list[Component]] = {}
    for c in comps:
        groups.setdefault(c.designator, []).append(c)

    # --- duplicate designators (deduped by UniqueId / multi-unit part) ----------
    for desig, members in groups.items():
        if len(members) < 2:
            continue
        distinct = {_identity(c) for c in members}
        if len(distinct) > 1:
            findings.append(
                Finding(
                    code="BOM_DUPLICATE_DESIGNATOR",
                    severity=Severity.ERROR,
                    message=(
                        f"designator {desig!r} is used by {len(distinct)} distinct "
                        f"components ({len(members)} placements)"
                    ),
                    refs=[desig],
                )
            )

    # --- refdes gaps (only within a numeric-suffixed prefix) --------------------
    by_prefix: dict[str, set[int]] = {}
    for desig in groups:  # one logical entry per designator
        parsed = _parse_refdes(desig)
        if parsed is None:  # compound / manually-named ref (e.g. J_USB_C) -> skip
            continue
        prefix, num = parsed
        by_prefix.setdefault(prefix, set()).add(num)

    for prefix in sorted(by_prefix):
        nums = by_prefix[prefix]
        lo, hi = min(nums), max(nums)
        missing = [n for n in range(lo, hi + 1) if n not in nums]
        if missing:
            refs = [f"{prefix}{n}" for n in missing]
            findings.append(
                Finding(
                    code="BOM_REFDES_GAP",
                    severity=Severity.NOTE,
                    message=(
                        f"refdes gap in {prefix!r} sequence ({prefix}{lo}..{prefix}{hi}): "
                        f"missing {', '.join(refs)}"
                    ),
                    refs=refs,
                )
            )

    # --- missing value / footprint (per logical component) ----------------------
    for desig, members in groups.items():
        has_value = any(_clean(c.value) for c in members)
        has_footprint = any(_clean(c.footprint) for c in members)
        if not has_value:
            findings.append(
                Finding(
                    code="BOM_MISSING_VALUE",
                    severity=Severity.WARNING,
                    message=f"component {desig} has no value",
                    refs=[desig],
                )
            )
        if not has_footprint:
            findings.append(
                Finding(
                    code="BOM_MISSING_FOOTPRINT",
                    severity=Severity.WARNING,
                    message=f"component {desig} has no footprint",
                    refs=[desig],
                )
            )

    return findings
