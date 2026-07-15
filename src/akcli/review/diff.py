"""``review diff`` — findings drift between two analysis runs (M7).

Alignment is by the wording-immune fingerprint, so message rewording never
shows up as churn; a finding without one falls back to (code, refs). The
verdict vocabulary: ``added`` (new in the second run), ``resolved`` (gone),
``severity_changed`` (same identity, different severity — a heuristic that
became datasheet-backed lands here too via the confidence field), and a
``persisting`` count.
"""

from __future__ import annotations


def _key(f: dict) -> str:
    fp = f.get("fingerprint")
    if fp:
        return fp
    return f.get("code", "") + "|" + "|".join(map(str, f.get("refs") or []))


def _index(doc: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in doc.get("findings", []):
        if isinstance(f, dict):
            out.setdefault(_key(f), f)
    return out


def _brief(f: dict) -> dict:
    return {"code": f.get("code"), "severity": f.get("severity"),
            "message": f.get("message"), "refs": list(f.get("refs") or []),
            "fingerprint": f.get("fingerprint")}


def diff_findings(old_doc: dict, new_doc: dict) -> dict:
    old, new = _index(old_doc), _index(new_doc)
    added = [_brief(new[k]) for k in sorted(new.keys() - old.keys())]
    resolved = [_brief(old[k]) for k in sorted(old.keys() - new.keys())]
    changed = []
    persisting = 0
    for k in sorted(old.keys() & new.keys()):
        o, n = old[k], new[k]
        if (o.get("severity") != n.get("severity")
                or o.get("confidence") != n.get("confidence")):
            changed.append({
                **_brief(n),
                "was": {"severity": o.get("severity"),
                        "confidence": o.get("confidence")},
                "now": {"severity": n.get("severity"),
                        "confidence": n.get("confidence")},
            })
        else:
            persisting += 1
    return {"added": added, "resolved": resolved,
            "severity_changed": changed, "persisting": persisting}


def render_text(d: dict) -> str:
    lines = [f"review diff: +{len(d['added'])} new, "
             f"−{len(d['resolved'])} resolved, "
             f"{len(d['severity_changed'])} changed, "
             f"{d['persisting']} persisting"]
    for f in d["added"]:
        lines.append(f"  + {str(f['severity']).upper()} [{f['code']}] "
                     f"{f['message']}")
    for f in d["resolved"]:
        lines.append(f"  - [{f['code']}] {f['message']}")
    for f in d["severity_changed"]:
        was, now = f["was"], f["now"]
        lines.append(f"  ~ [{f['code']}] {was['severity']}/"
                     f"{was['confidence']} -> {now['severity']}/"
                     f"{now['confidence']}: {f['message']}")
    return "\n".join(lines) + "\n"
