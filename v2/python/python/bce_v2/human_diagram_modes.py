"""Selectable recognition-diagram presentations."""

from enum import Enum


class DiagramMode(str, Enum):
    """Choose a transparent cube or opaque views from one or both corners."""

    TRANSPARENT = "transparent"
    OPPOSITE_CORNERS = "opposite-corners"
    SINGLE_CORNER = "single-corner"

    def __str__(self):
        return self.value
