"""CLI-layer contract of `akcli view`: no forced file binding.

Bare `view` serves the hub with nothing watched; `view live` without a path
auto-discovers the single .kicad_sch in the current directory (zero or many
candidates fail loudly). `server.serve` is stubbed — these tests never bind
a port or open a browser.
"""

from __future__ import annotations

import pytest

from akcli.cli import build_parser
from akcli.commands._shared import _ExitWith
from akcli.errors import EXIT
from akcli.webui import server


@pytest.fixture()
def serve_calls(monkeypatch):
    calls: list[dict] = []

    def fake_serve(**kwargs):
        calls.append(kwargs)
        return 0

    monkeypatch.setattr(server, "serve", fake_serve)
    return calls


def _run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


def test_bare_view_serves_hub_without_target(serve_calls):
    assert _run(["view", "--no-browser"]) == 0
    assert len(serve_calls) == 1
    assert "target" not in serve_calls[0]
    assert serve_calls[0]["open_browser"] is False


def test_view_calc_serves_without_target(serve_calls):
    assert _run(["view", "calc", "--no-browser"]) == 0
    assert "target" not in serve_calls[0]


def test_view_sch_shorthand_watches(serve_calls, tmp_path):
    sch = tmp_path / "board.kicad_sch"
    sch.write_text("(kicad_sch)", encoding="utf-8", newline="\n")
    assert _run(["view", str(sch), "--no-browser"]) == 0
    assert str(serve_calls[0]["target"]).endswith("board.kicad_sch")


def test_view_live_explicit_path(serve_calls, tmp_path):
    sch = tmp_path / "board.kicad_sch"
    sch.write_text("(kicad_sch)", encoding="utf-8", newline="\n")
    assert _run(["view", "live", str(sch), "--no-browser"]) == 0
    assert str(serve_calls[0]["target"]).endswith("board.kicad_sch")


def test_view_live_discovers_single_sch(serve_calls, tmp_path, monkeypatch):
    sch = tmp_path / "only.kicad_sch"
    sch.write_text("(kicad_sch)", encoding="utf-8", newline="\n")
    monkeypatch.chdir(tmp_path)
    assert _run(["view", "live", "--no-browser"]) == 0
    assert str(serve_calls[0]["target"]).endswith("only.kicad_sch")


def test_view_live_no_candidate_is_usage_error(serve_calls, tmp_path,
                                               monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(_ExitWith) as exc:
        _run(["view", "live", "--no-browser"])
    assert exc.value.code == EXIT["USAGE"]
    assert not serve_calls


def test_view_live_ambiguous_is_usage_error(serve_calls, tmp_path,
                                            monkeypatch):
    for name in ("a.kicad_sch", "b.kicad_sch"):
        (tmp_path / name).write_text("(kicad_sch)", encoding="utf-8",
                                     newline="\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(_ExitWith) as exc:
        _run(["view", "live", "--no-browser"])
    assert exc.value.code == EXIT["USAGE"]
    assert "a.kicad_sch" in str(exc.value)
    assert not serve_calls


def test_view_live_rejects_non_kicad_sch(serve_calls, tmp_path):
    other = tmp_path / "board.SchDoc"
    other.write_text("x", encoding="utf-8", newline="\n")
    with pytest.raises(_ExitWith) as exc:
        _run(["view", "live", str(other), "--no-browser"])
    assert exc.value.code == EXIT["USAGE"]


def test_view_bogus_argument_is_usage_error(serve_calls):
    with pytest.raises(_ExitWith) as exc:
        _run(["view", "bogus", "--no-browser"])
    assert exc.value.code == EXIT["USAGE"]
    assert not serve_calls
