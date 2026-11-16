from dataclasses import dataclass

from .message_data import PetlibroMessage


@dataclass
class WATER_CAP_EVENT(PetlibroMessage):
    """Water capacity event from device."""

    weightPercent: int = 0
    weight: int = 0
    radarDetected: bool = False
    batchIndex: int = 1
    totalBatches: int = 1


@dataclass
class ATTR_PUSH_EVENT(PetlibroMessage):
    """Attribute push event from device."""

    powerType: int | None = None
    electricQuantity: int | None = None
    batteryState: str = ""
    useWaterType: int | None = None
    lowWater: int | None = None
    wifiSsid: str | None = None
    enableLight: bool = False
    lightSwitch: bool = False
    lightAgingType: int | None = None
    filterNextReplacementTimestamp: int | None = None
    filterLedSwitch: int | None = None
    radarGain: int | None = None
    radarSensingThreshold: int | None = None
    waterStopSwitch: int | None = None
    sensingWaterDuration: int | None = None


@dataclass
class ATTR_SET_SERVICE(PetlibroMessage):
    """Service to set device attributes."""

    enableLight: bool = True
    lightSwitch: bool = True
    filterNextReplacementTimestamp: int | None = None

    def __init__(self, coverOpen: bool | None = None) -> None:
        """Initialize with cover state.

        Args:
            coverOpen: True to open, False to close, None for default
        """
        super().__init__()
        if coverOpen is not None:
            self.coverOpenMode = "KEEP_OPEN" if coverOpen else "KEEP_CLOSED"
