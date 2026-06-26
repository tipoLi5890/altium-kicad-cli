"""Render findings (+ metadata caveats) as text or JSON (SPEC §3.1).

A report ALWAYS prints a metadata header — passive-pin ratio, No-ERC suppressed
count, unnamed-net count and frac-coord presence — so that a vacuous "no findings"
pass is never mistaken for a clean board.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field


class Severity(enum.Enum):
    """Finding severity, ordered least -> most serious."""

    INFO = "info"
    NOTE = "note"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# rank for sorting (higher = more serious)
_SEV_RANK: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.NOTE: 1,
    Severity.WARNING: 2,
    Severity.ERROR: 3,
    Severity.CRITICAL: 4,
}


@dataclass
class Finding:
    """A single check result."""

    code: str
    severity: Severity
    message: str
    refs: list = field(default_factory=list)


# Metadata keys always surfaced in the header (with friendly labels + defaults).
_META_FIELDS: list[tuple[str, str, str]] = [
    ("passive_pin_ratio", "passive-pin ratio", "n/a"),
    ("no_erc_suppressed", "No-ERC suppressed", "0"),
    ("unnamed_net_count", "unnamed nets", "0"),
    ("frac_present", "frac coords present", "false"),
]


def _meta_dict(meta: dict | None) -> dict:
    meta = meta or {}
    out = {}
    for key, _label, default in _META_FIELDS:
        out[key] = meta.get(key, default)
    # preserve any extra metadata the caller passed
    for k, v in meta.items():
        out.setdefault(k, v)
    return out


def _render_text(findings: list[Finding], meta: dict) -> str:
    lines: list[str] = []
    lines.append("# metadata")
    for key, label, _default in _META_FIELDS:
        lines.append(f"  {label}: {meta[key]}")
    lines.append(f"# findings ({len(findings)})")
    if not findings:
        lines.append("  (none)")
    ordered = sorted(findings, key=lambda f: -_SEV_RANK.get(f.severity, 0))
    for f in ordered:
        sev = f.severity.value.upper()
        ref = f" {list(f.refs)}" if f.refs else ""
        lines.append(f"  {sev} [{f.code}] {f.message}{ref}")
    return "\n".join(lines)


def _render_json(findings: list[Finding], meta: dict) -> str:
    payload = {
        "metadata": meta,
        "findings": [
            {
                "code": f.code,
                "severity": f.severity.value,
                "message": f.message,
                "refs": list(f.refs),
            }
            for f in findings
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)


def render(findings: list[Finding], fmt: str = "text", meta: dict | None = None) -> str:
    """Render findings as ``"text"`` or ``"json"`` with an always-present metadata header."""
    m = _meta_dict(meta)
    if fmt == "json":
        return _render_json(findings, m)
    return _render_text(findings, m)
