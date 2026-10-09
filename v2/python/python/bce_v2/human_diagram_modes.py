"""Selectable recognition-diagram presentations."""

from enum import Enum


class DiagramMode(str, Enum):
    """Choose a transparent cube or opaque views from opposite corners."""

    TRANSPARENT = "transparent"
    OPPOSITE_CORNERS = "opposite-corners"

    def __str__(self):
        return self.value
