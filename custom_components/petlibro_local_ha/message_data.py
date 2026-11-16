import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from typing import Any

from .shared_const import TZ_OFFSET


@dataclass
class MQTTMessage:
    """Base class for MQTT messages with serialization utilities."""

    def to_mqtt_payload(self) -> str:
        """Convert the message to a JSON string.

        Returns:
            JSON string representation of the message
        """
        return json.dumps(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary, handling nested dataclasses.
        Returns:
            Dictionary representation of the message
        """
        result = {}
        for key, value in self.__dict__.items():
            if value is None:
                continue
            # Handle nested dataclasses
            if is_dataclass(value):
                result[key] = asdict(value)
            # Handle lists of dataclasses
            elif isinstance(value, list):
                result[key] = [
                    asdict(item) if is_dataclass(item) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def from_mqtt_payload(self, payload: dict[str, Any]) -> "MQTTMessage":
        """Deserialize the message from a dictionary payload.

        Args:
            payload: The payload dictionary containing message data

        Returns:
            Self with updated attributes
        """
        for key, value in payload.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self

    def __str__(self) -> str:
        """Return string representation."""
        return json.dumps(self.to_dict())


@dataclass
class PetlibroMessage(MQTTMessage):
    """Base class for Petlibro-specific messages."""

    cmd: str = field(init=False)
    ts: float = -1
    msgId: str = ""

    def __post_init__(self) -> None:
        """Set command after initialization."""
        self.cmd = self.__class__.__name__


@dataclass
class HEARTBEAT(PetlibroMessage):
    """Heartbeat message from device."""

    count: int | None = None
    rssi: int | None = None
    wifiType: int | None = None


@dataclass
class NTP_SYNC(PetlibroMessage):
    """NTP synchronization message."""

    def __init__(self) -> None:
        """Set timestamp and timezone during initialization."""
        super().__init__()
        now = datetime.now(UTC)
        self.ts = now.timestamp() * 1000

        # Get local timezone offset
        self.timezone = TZ_OFFSET

    timezone: int = 0


@dataclass
class NTP(PetlibroMessage):
    """NTP request message."""


@dataclass
class DEVICE_START_EVENT(PetlibroMessage):
    """Device start event."""

    success: bool = False
    pid: str | None = None
    mac: str | None = None
    hardwareVersion: str | None = None
    softwareVersion: str | None = None
    channelPlanNum: int | None = None
