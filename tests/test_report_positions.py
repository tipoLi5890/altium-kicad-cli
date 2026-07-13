"""Structured positions on findings: text ``@ (x,y)``, JSON pos/anchors, SARIF."""

from __future__ import annotations

import json

from altium_kicad_cli.report import Finding, Severity, anchor, render


def test_anchor_helper_shape():
    a = anchor("pin", "U1.3", (100, 200))
    assert a == {"kind": "pin", "id": "U1.3", "pos": (100.0, 200.0)}
    # pos is optional (a net anchor has no single coordinate)
    assert anchor("net", "GND") == {"kind": "net", "id": "GND"}


def test_text_appends_position():
    f = Finding("X", Severity.WARNING, "msg", refs=["U1.3"], pos=(150.0, 275.0))
    out = render([f], fmt="text")
    assert "@ (150,275)" in out
    # a positionless finding does not grow an @-clause
    out2 = render([Finding("Y", Severity.NOTE, "no pos")], fmt="text")
    assert "@" not in out2


def test_json_emits_pos_and_anchors_verbatim():
    f = Finding(
        "X", Severity.WARNING, "msg", refs=["U1.3"],
        pos=(150.0, 275.0), anchors=[anchor("pin", "U1.3", (150, 275))],
    )
    payload = json.loads(render([f], fmt="json"))
    fj = payload["findings"][0]
    assert fj["pos"] == [150.0, 275.0]
    assert fj["anchors"] == [{"kind": "pin", "id": "U1.3", "pos": [150.0, 275.0]}]


def test_json_positionless_finding_keeps_historical_shape():
    f = Finding("X", Severity.WARNING, "msg", refs=["R1.2"])
    fj = json.loads(render([f], fmt="json"))["findings"][0]
    assert fj == {"code": "X", "severity": "warning", "message": "msg",
                  "refs": ["R1.2"]}
    assert "pos" not in fj and "anchors" not in fj


def test_sarif_logical_locations_and_properties_but_stable_fingerprint():
    plain = Finding("X", Severity.WARNING, "msg", refs=["U1.3"])
    placed = Finding("X", Severity.WARNING, "msg", refs=["U1.3"],
                     pos=(10, 20), anchors=[anchor("pin", "U1.3", (10, 20))])
    fp_plain = json.loads(render([plain], "sarif", {}, source="s.kicad_sch"))[
        "runs"][0]["results"][0]["partialFingerprints"]["akcliFinding/v1"]
    r = json.loads(render([placed], "sarif", {}, source="s.kicad_sch"))[
        "runs"][0]["results"][0]
    # position must NOT perturb the fingerprint (alert identity stays stable)
    assert r["partialFingerprints"]["akcliFinding/v1"] == fp_plain
    logical = r["locations"][0]["logicalLocations"]
    assert logical == [{"name": "U1.3", "kind": "pin"}]
    assert r["properties"]["akcli"]["pos"] == [10, 20]
    assert r["properties"]["akcli"]["anchors"][0]["kind"] == "pin"
