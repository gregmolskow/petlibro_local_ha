"""Constants for the Petlibro PLWF116 water fountain."""

from __future__ import annotations

from enum import Enum


class WaterFountainState(Enum):
    """Enum for the different states of the PLWF116 water fountain."""

    RUNNING = 0
    IDLE = 1
    WARNING = 2
    ERROR = 3
    UNKNOWN = 4

    def __str__(self) -> str:
        """Return string representation."""
        return self.name.lower()


# Error codes
ERROR_LOW_WATER = "low_water"
ERROR_FILTER_REPLACE = "filter_replace"
ERROR_PUMP_FAULT = "pump_fault"
ERROR_UNKNOWN = "unknown"
ERROR_NONE = "none"
