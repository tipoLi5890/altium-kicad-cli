"""Detector modules — importing this package registers every detector.

Families land per milestone (see the review integration plan): ``signal``
(M2), ``validation`` (M3), ``pcb``/``cross`` (M5+), ``emc`` (M6),
``domain`` (M8).
"""

from . import domain, emc, gerber, pcb, signal, validation  # noqa: F401 — registration side effect
