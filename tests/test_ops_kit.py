"""Tests for the op-list authoring kit (`akcli ops list|template`).

Includes the drift guard: the in-code required/optional tables must match
``schemas/ops.schema.json`` so `ops template` never teaches a stale shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from altium_kicad_cli import cli, ops

SCHEMA = json.loads(
    (Path(__file__).parent.parent / "schemas" / "ops.schema.json").read_text()
)


def _schema_ops() -> dict[str, dict]:
    """{op name: its schema branch} from the anyOf/oneOf op union."""
    out = {}
    stack = [SCHEMA]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            props = node.get("properties", {})
            op_const = props.get("op", {}).get("const")
            if op_const:
                out[op_const] = node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return out


def test_tables_match_schema():
    branches = _schema_ops()
    # every schema op is in OP_NAMES (sugar ops may share the power-port branch)
    for name, branch in branches.items():
        assert name in ops.OP_NAMES, f"schema op {name!r} missing from OP_NAMES"
        required = [f for f in branch.get("required", []) if f != "op"]
        assert sorted(ops._OP_REQUIRED.get(name, [])) == sorted(required), (
            f"{name}: required fields drifted from schema"
        )
        schema_fields = set(branch.get("properties", {})) - {"op"}
        known = set(ops._OP_REQUIRED.get(name, [])) | set(ops._OP_OPTIONAL.get(name, {}))
        unknown = known - schema_fields
        assert not unknown, f"{name}: kit fields {unknown} not in schema"


def test_template_fills_required_fields():
    for name in sorted(ops.OP_NAMES):
        op = ops.op_template(name)
        assert op["op"] == name
        for field in ops._OP_REQUIRED.get(name, []):
            assert field in op, f"{name}: template misses required {field!r}"


def test_cli_ops_list(capsys):
    assert cli.main(["ops", "list"]) == 0
    out = capsys.readouterr().out
    assert "place_component" in out and "delete_object" in out
    assert "required:" in out


def test_cli_ops_template(capsys):
    assert cli.main(["ops", "template", "move_component"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["protocol_version"] == ops.PROTOCOL_VERSION
    (op,) = doc["ops"]
    assert op["op"] == "move_component"
    assert {"designator", "x_mil", "y_mil"} <= set(op)


def test_cli_ops_template_unknown_op(capsys):
    assert cli.main(["ops", "template", "not_an_op"]) == 2


def test_cli_ops_bare_is_usage(capsys):
    assert cli.main(["ops"]) == 2
