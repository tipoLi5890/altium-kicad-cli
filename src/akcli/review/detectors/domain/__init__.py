"""Domain-family detectors (M8): interface-specific rules.

First family: USB-C. RF / Ethernet / HDMI / memory / BMS / motor remain on
the demand-ordered backlog — a family lands when a real board needs it, not
before.
"""

from . import usb  # noqa: F401
