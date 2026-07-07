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
    from .model import SCHEMA_VERSION  # local import avoids any import cycle
    payload = {
        "schema_version": SCHEMA_VERSION,
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


# SARIF severity levels (GitHub code scanning): error / warning / note.
_SARIF_LEVEL = {
    Severity.CRITICAL: "error",
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.NOTE: "note",
    Severity.INFO: "note",
}


def _render_sarif(findings: list[Finding], meta: dict, source: str | None) -> str:
    """SARIF 2.1.0 for GitHub code scanning / other SARIF consumers.

    Schematic findings have no line numbers, so locations carry only the
    artifact URI; ``partialFingerprints`` keeps alert identity stable across
    runs for the same (code, message, refs) triple.
    """
    import hashlib

    from . import __version__
    from .model import SCHEMA_VERSION

    rules: dict[str, dict] = {}
    results = []
    for f in sorted(findings, key=lambda f: (-_SEV_RANK.get(f.severity, 0), f.code)):
        rules.setdefault(f.code, {
            "id": f.code,
            "shortDescription": {"text": f.code.replace("_", " ").title()},
        })
        fp = hashlib.sha256(
            "|".join([f.code, f.message, *map(str, f.refs)]).encode("utf-8")
        ).hexdigest()[:32]
        text = f.message
        if f.refs:
            text += " (refs: " + ", ".join(map(str, f.refs)) + ")"
        result: dict = {
            "ruleId": f.code,
            "level": _SARIF_LEVEL.get(f.severity, "note"),
            "message": {"text": text},
            "partialFingerprints": {"akcliFinding/v1": fp},
        }
        if source:
            result["locations"] = [{
                "physicalLocation": {
                    "artifactLocation": {"uri": str(source).replace("\\", "/")}
                }
            }]
        results.append(result)

    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "akcli",
                "informationUri": "https://github.com/tipoLi5890/altium-kicad-cli",
                "version": __version__,
                "rules": list(rules.values()),
            }},
            "properties": {"schema_version": SCHEMA_VERSION, "metadata": meta},
            "results": results,
        }],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _xml_escape(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _render_junit(findings: list[Finding], meta: dict, source: str | None) -> str:
    """JUnit XML for CI test reporters.

    Each WARNING+ finding is a failed testcase; NOTE/INFO become passed
    testcases carrying their text in ``system-out``; a clean run emits one
    passed "no findings" case so the suite is never empty.
    """
    cases: list[str] = []
    failures = 0
    ordered = sorted(findings, key=lambda f: (-_SEV_RANK.get(f.severity, 0), f.code))
    for f in ordered:
        name = _xml_escape(f.message[:200])
        cls = f"akcli.{_xml_escape(f.code)}"
        body = _xml_escape(f.message)
        if f.refs:
            body += "\nrefs: " + _xml_escape(", ".join(map(str, f.refs)))
        if _SEV_RANK.get(f.severity, 0) >= _SEV_RANK[Severity.WARNING]:
            failures += 1
            cases.append(
                f'    <testcase classname="{cls}" name="{name}">\n'
                f'      <failure message="{_xml_escape(f.severity.value)}">{body}</failure>\n'
                f"    </testcase>"
            )
        else:
            cases.append(
                f'    <testcase classname="{cls}" name="{name}">\n'
                f"      <system-out>{body}</system-out>\n"
                f"    </testcase>"
            )
    if not cases:
        cases.append('    <testcase classname="akcli" name="no findings"/>')

    suite_name = _xml_escape(source or "akcli-check")
    total = max(len(findings), 1)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuites tests="{total}" failures="{failures}">\n'
        f'  <testsuite name="{suite_name}" tests="{total}" failures="{failures}">\n'
        + "\n".join(cases)
        + "\n  </testsuite>\n</testsuites>\n"
    )


def render(
    findings: list[Finding],
    fmt: str = "text",
    meta: dict | None = None,
    source: str | None = None,
) -> str:
    """Render findings as ``text``/``json`` (metadata header always present) or
    ``sarif`` (GitHub code scanning) / ``junit`` (CI test reporters)."""
    m = _meta_dict(meta)
    if fmt == "json":
        return _render_json(findings, m)
    if fmt == "sarif":
        return _render_sarif(findings, m, source)
    if fmt == "junit":
        return _render_junit(findings, m, source)
    return _render_text(findings, m)
