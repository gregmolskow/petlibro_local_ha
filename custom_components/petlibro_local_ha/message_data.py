"""message_data.py

This module defines dataclasses for various MQTT messages and events used
by the Petlibro smart feeder integration.
It provides serialization and deserialization methods for MQTT payloads,
as well as structures for device events,
feeding plans, and service commands.

Classes:
    MQTTMessage: Base class for MQTT messages with serialization utilities.
    PetlibroMessage: Base class for Petlibro-specific messages.
    GRAIN_OUTPUT_EVENT: Represents a grain output event.
    WAREHOUSE_DOOR_EVENT: Represents a warehouse door event.
    ATTR_PUSH_EVENT: Represents an attribute push event from the device.
    DEVICE_START_EVENT: Represents a device start event.
    HEARTBEAT: Represents a heartbeat message from the device.
    MANUAL_FEEDING_SERVICE: Represents a manual feeding command.
    NTP_SYNC: Represents an NTP synchronization message.
    NTP: Represents an NTP request message.
    ATTR_SET_SERVICE: Represents a service to set device attributes.
    FoodPlan: Represents a single feeding plan.
    FEEDING_PLAN_SERVICE: Represents a service to manage feeding plans.
    DEVICE_FEEDING_PLAN_SERVICE: Represents a request to get the feeding plan from the device.

Usage:
    Use these classes to create, serialize, and parse MQTT messages for communication
    with Petlibro devices.
"""

import datetime
import json
from dataclasses import dataclass


@dataclass
class MQTTMessage:
    """Base class for MQTT messages with serialization utilities."""

    def to_mqtt_payload(self) -> str:
        """Convert the message to a JSON string with a timestamp.

        Returns:
            str: JSON string representation of the message.

        """
        return json.dumps(self.__dict__)

    def from_mqtt_payload(self, payload: dict) -> "MQTTMessage":
        """Deserialize the message from a dictionary payload.

        Args:
            payload (dict): The payload dictionary containing message data.

        Returns:
            Message (MQTTMessage): Returns the instance of the class with updated attributes.

        """
        for val in self.__dict__:
            if payload.get(val) is not None:
                setattr(self, val, payload.get(val))
        return self

    def __str__(self):
        return json.dumps(self.__dict__)


@dataclass
class PetlibroMessage(MQTTMessage):
    """Base class for Petlibro-specific messages.

    This class extends MQTTMessage and provides a common structure for Petlibro messages.
    It includes a command type, timestamp, and message ID.

    """

    def __init__(self):
        self.cmd: str = self.msType
        self.ts: float = -1
        self.msgId: str = ""

    @property
    def msType(self) -> str:
        """Return the type of the message as a string.

        Returns:
            str: The name of the class, which serves as the message type.

        """
        return self.__class__.__name__


@dataclass
class GRAIN_OUTPUT_EVENT(PetlibroMessage):
    """Represents a grain output event from the Petlibro device."""

    finished: bool
    type: str
    actualGrainNum: int
    expectGrainNum: int
    execTime: int
    execStep: str


@dataclass
class WAREHOUSE_DOOR_EVENT(PetlibroMessage):
    """Represents a warehouse door event from the Petlibro device."""

    barnDoorState: bool
    triggerType: str
    execTime: int


@dataclass
class ATTR_PUSH_EVENT(PetlibroMessage):
    """Represents an attribute push event from the Petlibro device."""

    def __init__(self):
        super().__init__()
        self.powerMode: int | None = None
        self.powerType: int | None = None
        self.electricQuantity: int | None = None
        self.surplusGrain: bool | None = False
        self.barnDoorState: bool | None = False
        self.motorState: int | None = None
        self.grainOutletState: bool = False
        self.wifiSsid: str | None = None
        self.audioUrl: str | None = None
        self.enableAudio: bool = False
        self.volume: int | None = None
        self.coverOpenMode: str | None = None
        self.coverCloseSpeed: str | None = None
        self.coverClosePosition: int | None = None
        self.childLockSwitch: bool = False
        self.childLockLockDuration: int | None = None
        self.childLockUnlockDuration: int | None = None
        self.closeDoorTimeSec: int | None = None
        self.enableScreenDisplay: bool = False
        self.screenDisplaySwitch: bool = False
        self.screenDisplayAgingType: int | None = None
        self.screenDisplayInterval: int | None = None
        self.enableKeyTimeShare: bool = False
        self.CoilState: bool = False
        self.enableSound: bool = False
        self.soundSwitch: bool = False
        self.soundAgingType: int | None = None
        self.autoChangeType: int | None = None
        self.autoThreshold: int | None = None


@dataclass
class DEVICE_START_EVENT(PetlibroMessage):
    """Represents a device start event from the Petlibro device."""

    def __init__(self):
        super().__init__()
        self.success: bool = False
        self.pid: str | None = None
        self.mac: str | None = None
        self.hardwareVersion: str | None = None
        self.softwareVersion: str | None = None
        self.channelPlanNum: int | None = None


@dataclass
class HEARTBEAT(PetlibroMessage):
    """Represents a heartbeat message from the Petlibro device."""

    def __init__(self):
        super().__init__()
        self.count: int | None = None
        self.rssi: int | None = None
        self.wifiType: int | None = None


@dataclass
class MANUAL_FEEDING_SERVICE(PetlibroMessage):
    """Represents a manual feeding command for the Petlibro device."""

    def __init__(self):
        super().__init__()
        self.grainNum: int = 0


@dataclass
class NTP_SYNC(PetlibroMessage):
    """Represents an NTP synchronization message for the Petlibro device."""

    def __init__(self):
        super().__init__()
        self.ts = datetime.datetime.now().timestamp() * 1000  # noqa: DTZ005
        self.timezone = int(
            datetime.datetime.now().astimezone().utcoffset().total_seconds()
            / 3600,  # type: ignore
        )


@dataclass
class NTP(PetlibroMessage):
    """Represents an NTP request message for the Petlibro device."""

    def __init__(self):
        super().__init__()


@dataclass
class ATTR_SET_SERVICE(PetlibroMessage):
    """Represents a service to set device attributes for the Petlibro device."""

    def __init__(self, coverOpen: bool | None = None):
        super().__init__()
        self.coverOpenMode = "KEEP_OPEN" if coverOpen else "KEEP_CLOSED"


@dataclass
class FoodPlan(MQTTMessage):
    """Represents a single feeding plan for the Petlibro device.
    Still in dev
    """

    grainNum: int | None
    executionTime: str | None
    planId: int | None
    enableAudio: bool | None
    audioTimes: int | None
    syncTime: int | None

    def __init__(  # noqa: PLR0917
        self,
        grainNum: int = 0,
        executionTime: str = "",
        planId: int = 0,
        enableAudio: bool = False,
        audioTimes: int = 0,
        syncTime: int = 0,
    ):
        self.grainNum = grainNum
        self.executionTime = executionTime
        self.planId = planId
        self.enableAudio = enableAudio
        self.audioTimes = audioTimes
        self.syncTime = syncTime


@dataclass
class FEEDING_PLAN_SERVICE(PetlibroMessage):
    """This command sets the feeding plan for the device"""

    def __init__(self):
        super().__init__()
        self.plans: list[FoodPlan] = []

    def add_plan(self, plan: FoodPlan):
        """Add a feeding plan to the service.

        Args:
            plan (FoodPlan): The feeding plan to add.

        """
        if plan.planId is None:
            # planID starts at 1, not 0
            plan.planId = len(self.plans) + 1
        self.plans.append(plan)

    def remove_plan(self, index: int) -> FoodPlan:
        """Remove a feeding plan by its index.

        Args:
            index (int): The index of the plan to remove.

        Returns:
            FoodPlan: The removed feeding plan.

        Raises:
            IndexError: If the index is out of range.

        """
        return self.plans.pop(index)

    def update_plan(self, plan: FoodPlan):
        """Update an existing feeding plan."""
        assert plan.planId is not None, "Plan ID must be set for update"
        self.plans[plan.planId] = plan

    def from_mqtt_payload(self, payload) -> "FEEDING_PLAN_SERVICE":
        """Deserialize the feeding plan service from a dictionary payload.

        Args:
            payload (dict): The payload dictionary containing feeding plan data.

        Returns:
            FEEDING_PLAN_SERVICE: Returns the instance of the class with updated attributes.

        """
        for val in self.__dict__:
            new_val = payload.get(val)
            if val == "plans":
                for plan in new_val:  # type: ignore
                    tmp = FoodPlan()
                    tmp.from_mqtt_payload(plan)
                    # Not sure if this should be update or add
                    self.update_plan(tmp)
            if new_val is not None:
                setattr(self, val, payload.get(val))
        return self


class DEVICE_FEEDING_PLAN_SERVICE(PetlibroMessage):
    """This class gets the feeding plan from the device"""

    def __init__(self):
        super().__init__()


if __name__ == "__main__":
    test = MANUAL_FEEDING_SERVICE()
    print(test.to_mqtt_payload())
