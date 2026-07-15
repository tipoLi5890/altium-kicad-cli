"""EMC-family detectors (M6): pre-compliance risk, three batches.

Batch 1 (geometric): ground plane presence/coverage, via stitching,
board-edge tracks, TVS-to-connector distance. Batch 2 (analytical):
differential-pair skew, clock-net edge routing. Batch 3 (stackup): adjacent
signal layers. Every threshold is an assumption stated on the finding;
the engine aggregates an advisory risk score — never a compliance verdict.
"""

from . import diffpair, edge, planes, protection, stitching  # noqa: F401
