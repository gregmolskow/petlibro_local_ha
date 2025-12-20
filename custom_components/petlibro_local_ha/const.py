"""Constants and enums for the Petlibro MQTT Home Assistant integration.

This module defines the State enum for the PLAF301 cat feeder and loads the domain name from pyproject.toml.
"""

import enum
from pathlib import Path

import toml
from homeassistant.components.vacuum import VacuumActivity

HERE = Path(Path(__file__).resolve()).parent

# Dynamically get the doain infomration from pyproject.toml
pyproject_path = Path(f"{HERE}/../pyproject.toml")
with pyproject_path.open("r", encoding="utf-8") as f:
    pyproject_data = toml.load(f)
DOMAIN = pyproject_data["project"].get("name")
# DOMAIN = "petlibro_mqtt_ha"


class State(enum.Enum):
    """Enum for the different states of the PLAF301 cat feeder."""

    DISPENSING = 0  # cleaning
    ERROR = 1  # error
    DOOR_OPEN = 3  # docked
    DOOR_CLOSED = 2  # idle
    UNKNOWN = 4

    def toHA(self) -> str:
        """Convert the state value to a Home Assistant compatible JSON string.
        :return: String representation of the state.
        :rtype: str
        """
        out = VacuumActivity.ERROR
        if self.value == 0:
            out = VacuumActivity.CLEANING
        elif self.value == 1 | 4:
            out = VacuumActivity.ERROR
        elif self.value == 2:  # noqa: PLR2004
            out = VacuumActivity.IDLE
        elif self.value == 3:  # noqa: PLR2004
            out = VacuumActivity.DOCKED

        return out
