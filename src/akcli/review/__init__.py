"""``akcli review`` — engineering design review over the normalized model.

Detectors find *engineering* risks the structural checks (:mod:`..checks`)
cannot express: implausible feedback dividers, unloaded crystals, unprotected
connectors, filter corners, cross-domain signals. Every detector consumes the
format-agnostic :class:`~..model.Schematic` — so a rule written once reviews
KiCad **and** Altium inputs — and emits :class:`~..report.Finding` objects
carrying the review evidence envelope (confidence / evidence / fingerprint),
rendered by the same ``report`` machinery as ``check`` (no parallel
mechanism).

Every rule cites the engineering literature its judgement rests on (see
``docs/review-rules.md`` and ``review explain``). Findings default to
ADVISORY: ``review analyze`` exits 0 regardless of findings unless
``--fail-on`` opts in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

__all__ = ["Rule", "Detector", "DETECTORS", "PROFILES", "register",
           "rules_index"]


@dataclass(frozen=True)
class Rule:
    """One review rule: frozen code + the explanation ``review explain`` prints.

    ``reference`` cites the engineering source the rule's judgement rests on
    (spec clause, application note, textbook); ``None`` marks a pure
    topology-consistency rule that needs no external authority.
    """

    code: str
    title: str
    explain: str
    default_severity: str = "warning"
    confidence: str = "heuristic"
    version: str = "1"
    reference: str | None = None


@dataclass(frozen=True)
class Detector:
    """A named detector: ``run(ctx) -> list[Finding]`` plus its rule set."""

    name: str                        # e.g. "signal.divider"
    family: str                      # signal | validation | pcb | cross | emc | domain
    run: Callable
    rules: tuple[Rule, ...] = field(default_factory=tuple)


DETECTORS: dict[str, Detector] = {}

# Which detector FAMILIES each profile runs. Families land incrementally
# (M2: signal; M3: validation; M5+: pcb/cross; M6: emc; M8: domain) — a
# profile naming a family with no registered detectors simply runs fewer.
PROFILES: dict[str, tuple[str, ...]] = {
    "fast": ("signal",),
    "standard": ("signal", "validation", "pcb", "gerber"),
    "deep": ("signal", "validation", "pcb", "cross", "emc", "domain",
             "gerber"),
}


def register(det: Detector) -> Detector:
    """Register a detector (module import time); duplicate names are a bug."""
    if det.name in DETECTORS:
        raise ValueError(f"duplicate detector {det.name!r}")
    DETECTORS[det.name] = det
    return det


def rules_index() -> dict[str, Rule]:
    """``{code: Rule}`` across every registered detector (for ``explain``)."""
    from . import detectors  # noqa: F401 — import triggers registration
    out: dict[str, Rule] = {}
    for det in DETECTORS.values():
        for rule in det.rules:
            out[rule.code] = rule
    return out
