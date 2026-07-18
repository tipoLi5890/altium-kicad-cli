"""Real-board corpus regression: the solestack insole pod (88 parts, 10 groups).

This board is the reason two 0.12.x-era safety features exist:

* its wires cross group borders, so a rigid `arrange --groups --apply` would
  have silently MERGED a power rail into GND — the net-preservation gate now
  refuses that write;
* `--propose-labels` turns that refusal into a label-on-pin + redundant-wire
  repair draft, after which the same re-pack applies net-preserved.

Keeping the full loop green on the real board is the point of this file.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from akcli import netdiff
from akcli.cli import main
from akcli.readers import kicad as kreader

BOARD = Path(__file__).parent / "fixtures" / "corpus" / "pod_insole.kicad_sch"


@pytest.fixture()
def pod(tmp_path: Path) -> Path:
    tgt = tmp_path / "pod.kicad_sch"
    shutil.copy2(BOARD, tgt)
    return tgt


def test_reads_with_expected_census():
    sch = kreader.read_sch(str(BOARD))
    assert len(sch.components) == 88
    assert len(sch.nets) == 89
    groups = {c.parameters.get("Group") for c in sch.components
              if c.parameters.get("Group")}
    assert len(groups) == 10


def test_direct_regroup_is_refused(pod: Path, capsys):
    # wired across group borders -> the gate must refuse (this exact board
    # produced a rail-to-GND merge before the gate existed)
    before = pod.read_bytes()
    rc = main(["arrange", str(pod), "--groups", "--apply",
               "--group-gap", "1000", "--page-width", "20000"])
    err = capsys.readouterr().err
    assert rc == 6
    assert "REFUSED" in err and "netlist" in err
    assert pod.read_bytes() == before


def test_propose_then_regroup_succeeds_net_preserved(pod: Path, capsys):
    orig_nets = kreader.read_sch(str(pod)).nets
    draft = pod.parent / "labels.json"
    assert main(["arrange", str(pod), "--groups",
                 "--propose-labels", str(draft)]) == 0
    capsys.readouterr()
    assert main(["draw", str(pod), "--ops", str(draft), "--apply"]) == 0
    assert main(["arrange", str(pod), "--groups", "--apply",
                 "--group-gap", "1000", "--page-width", "20000"]) == 0
    capsys.readouterr()
    now = kreader.read_sch(str(pod))
    d = netdiff.diff(orig_nets, now.nets)
    assert d.equivalent, netdiff.format_summary(d)
    # the 2D packing honored the 1000 mil channel between group blocks
    boxes: dict[str, list[float]] = {}
    for c in now.components:
        g = c.parameters.get("Group")
        if not g:
            continue
        b = boxes.setdefault(g, [c.x_mil, c.y_mil, c.x_mil, c.y_mil])
        b[0], b[1] = min(b[0], c.x_mil), min(b[1], c.y_mil)
        b[2], b[3] = max(b[2], c.x_mil), max(b[3], c.y_mil)
    names = sorted(boxes)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ax0, ay0, ax1, ay1 = boxes[a]
            bx0, by0, bx1, by1 = boxes[b]
            gap = max(max(bx0 - ax1, ax0 - bx1), max(by0 - ay1, ay0 - by1))
            assert gap > 0, f"groups {a}/{b} overlap after re-pack"
