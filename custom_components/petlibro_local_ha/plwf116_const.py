"""Constants for the Petlibro MQTT Home Assistant integration."""

from __future__ import annotations

from enum import Enum

from homeassistant.components.vacuum import VacuumActivity


class FeederState(Enum):
    """Enum for the different states of the PLAF301 cat feeder."""

    DISPENSING = 0
    ERROR = 1
    DOOR_CLOSED = 2
    DOOR_OPEN = 3
    UNKNOWN = 4

    def to_ha_activity(self) -> VacuumActivity:
        """Convert feeder state to Home Assistant VacuumActivity.

        Returns:
            VacuumActivity: Corresponding HA vacuum activity state
        """
        state_mapping = {
            FeederState.DISPENSING: VacuumActivity.CLEANING,
            FeederState.ERROR: VacuumActivity.ERROR,
            FeederState.DOOR_CLOSED: VacuumActivity.IDLE,
            FeederState.DOOR_OPEN: VacuumActivity.DOCKED,
            FeederState.UNKNOWN: VacuumActivity.ERROR,
        }
        return state_mapping.get(self, VacuumActivity.ERROR)


# Error codes
ERROR_EMPTY = "empty"
ERROR_CLOGGED = "clogged"
ERROR_UNKNOWN = "unknown"
ERROR_NONE = "none"
