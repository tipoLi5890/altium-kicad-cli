"""``akcli library check-lock`` — queryable GUI-open guard for external flows.

akcli's own writes refuse a locked target; this exposes the same ``~<name>.lck``
check so hand scripts / ``sed`` can gate before touching a file KiCad holds open
(a GUI save would overwrite an external edit).
"""

from __future__ import annotations

import json

from akcli import cli


def _sch(tmp_path, name="board.kicad_sch"):
    f = tmp_path / name
    f.write_text('(kicad_sch (version 20231120) (generator "akcli") '
                 '(uuid "55555555-6666-7777-8888-999999999999") (paper "A4"))\n')
    return f


def test_clean_tree_is_writable(tmp_path, capsys):
    _sch(tmp_path)
    assert cli.main(["library", "check-lock", str(tmp_path)]) == 0
    assert "none open" in capsys.readouterr().out


def test_lock_present_exits_6(tmp_path, capsys):
    f = _sch(tmp_path)
    (tmp_path / f"~{f.name}.lck").write_text("")     # KiCad-style GUI lock
    assert cli.main(["library", "check-lock", str(tmp_path)]) == 6
    out = capsys.readouterr().out
    assert "LOCKED" in out and f.name in out


def test_json_reports_locked_list(tmp_path, capsys):
    f = _sch(tmp_path)
    (tmp_path / f"~{f.name}.lck").write_text("")
    assert cli.main(["library", "check-lock", str(tmp_path), "--json"]) == 6
    doc = json.loads(capsys.readouterr().out)
    assert doc["writable"] is False
    assert doc["scanned"] == 1
    assert len(doc["locked"]) == 1 and doc["locked"][0]["file"].endswith(f.name)


def test_missing_project_is_not_found(tmp_path):
    assert cli.main(["library", "check-lock", str(tmp_path / "nope")]) == 4
