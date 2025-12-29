"""Constants for the Petlibro MQTT Home Assistant integration."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum

from homeassistant.components.vacuum import VacuumActivity

DOMAIN = "petlibro_local_ha"

# Default update interval (minutes)
DEFAULT_SCAN_INTERVAL = 5

# MQTT topics
TOPIC_DEVICE_EVENT = "dl/{model}/{sn}/device/event/post"
TOPIC_DEVICE_CONTROL = "dl/{model}/{sn}/device/service/sub"
TOPIC_DEVICE_CONTROL_IN = "dl/{model}/{sn}/device/service/post"
TOPIC_DEVICE_HEARTBEAT = "dl/{model}/{sn}/device/heart/post"

_LOGGER = logging.getLogger(__name__)

# Device model
MODEL_PLAF301 = "PLAF301"
MANUFACTURER = "Petlibro"

# Get local timezone
TZ = datetime.now().astimezone().tzinfo

# Get timezone offset in hours
TZ_OFFSET = datetime.now().astimezone().utcoffset().total_seconds() / 3600


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
