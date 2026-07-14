"""KiCad ``{token}`` name escaping (``kicad_escape``)."""

from __future__ import annotations

import pytest

from akcli.kicad_escape import escape_lib_id, escape_string, unescape_string


@pytest.mark.parametrize("escaped,raw", [
    ("19-237{slash}R6GHBHC-A04{slash}2T", "19-237/R6GHBHC-A04/2T"),
    ("SMD1812P050TF{slash}30", "SMD1812P050TF/30"),
    ('A{dblquote}B', 'A"B'),
    ("A{backslash}B", "A\\B"),
    ("A{brace}B", "A{B"),
    ("A{lt}B{gt}C", "A<B>C"),
    ("A{colon}B", "A:B"),
    ("plain_Name-1", "plain_Name-1"),
])
def test_unescape(escaped, raw):
    assert unescape_string(escaped) == raw


def test_unescape_passthrough():
    assert unescape_string(None) is None
    assert unescape_string("") == ""
    assert unescape_string("no tokens here") == "no tokens here"
    # an unknown / unterminated token is left literal
    assert unescape_string("A{unknown}B") == "A{unknown}B"
    assert unescape_string("A{slash") == "A{slash"


@pytest.mark.parametrize("raw,escaped", [
    ("19-237/R6GHBHC-A04/2T", "19-237{slash}R6GHBHC-A04{slash}2T"),
    ('A"B', 'A{dblquote}B'),
    ("A{B", "A{brace}B"),          # the introducer itself must escape
    ("plain_Name-1", "plain_Name-1"),
])
def test_escape(raw, escaped):
    assert escape_string(raw) == escaped


def test_escape_lib_id_preserves_separator():
    # the ':' between nickname and name stays literal; a ':' inside a part escapes
    assert escape_lib_id("proj_jlc:19-237/x") == "proj_jlc:19-237{slash}x"
    assert escape_lib_id("Device:R") == "Device:R"
    assert escape_lib_id("nick:a:b") == "nick:a{colon}b"


@pytest.mark.parametrize("name", [
    "19-237/R6GHBHC-A04/2T", 'weird"{name}/x', "Device:R", "simple",
])
def test_round_trip(name):
    assert unescape_string(escape_string(name)) == name
