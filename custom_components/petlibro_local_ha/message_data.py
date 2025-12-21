"""MQTT message data structures for Petlibro integration.

This module defines dataclasses for various MQTT messages and events used
by the Petlibro smart feeder integration.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any


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
        """Convert message to dictionary.

        Returns:
            Dictionary representation of the message
        """
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def from_mqtt_payload(self, payload: dict[str, Any]) -> MQTTMessage:
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
class GRAIN_OUTPUT_EVENT(PetlibroMessage):
    """Grain output event from device."""

    finished: bool = False
    type: str = ""
    actualGrainNum: int = 0
    expectGrainNum: int = 0
    execTime: int = 0
    execStep: str = ""


@dataclass
class WAREHOUSE_DOOR_EVENT(PetlibroMessage):
    """Warehouse door event from device."""

    barnDoorState: bool = False
    triggerType: str = ""
    execTime: int = 0


@dataclass
class ATTR_PUSH_EVENT(PetlibroMessage):
    """Attribute push event from device."""

    powerMode: int | None = None
    powerType: int | None = None
    electricQuantity: int | None = None
    surplusGrain: bool = False
    barnDoorState: bool = False
    motorState: int | None = None
    grainOutletState: bool = False
    wifiSsid: str | None = None
    audioUrl: str | None = None
    enableAudio: bool = False
    volume: int | None = None
    coverOpenMode: str | None = None
    coverCloseSpeed: str | None = None
    coverClosePosition: int | None = None
    childLockSwitch: bool = False
    childLockLockDuration: int | None = None
    childLockUnlockDuration: int | None = None
    closeDoorTimeSec: int | None = None
    enableScreenDisplay: bool = False
    screenDisplaySwitch: bool = False
    screenDisplayAgingType: int | None = None
    screenDisplayInterval: int | None = None
    enableKeyTimeShare: bool = False
    CoilState: bool = False
    enableSound: bool = False
    soundSwitch: bool = False
    soundAgingType: int | None = None
    autoChangeType: int | None = None
    autoThreshold: int | None = None


@dataclass
class DEVICE_START_EVENT(PetlibroMessage):
    """Device start event."""

    success: bool = False
    pid: str | None = None
    mac: str | None = None
    hardwareVersion: str | None = None
    softwareVersion: str | None = None
    channelPlanNum: int | None = None


@dataclass
class HEARTBEAT(PetlibroMessage):
    """Heartbeat message from device."""

    count: int | None = None
    rssi: int | None = None
    wifiType: int | None = None


@dataclass
class MANUAL_FEEDING_SERVICE(PetlibroMessage):
    """Manual feeding command."""

    grainNum: int = 1


@dataclass
class NTP_SYNC(PetlibroMessage):
    """NTP synchronization message."""

    def __post_init__(self) -> None:
        """Set timestamp and timezone after initialization."""
        super().__post_init__()
        now = datetime.datetime.now(datetime.UTC)
        self.ts = now.timestamp() * 1000

        # Get local timezone offset
        local_now = datetime.datetime.now().astimezone()
        offset = local_now.utcoffset()
        self.timezone = int(offset.total_seconds() / 3600) if offset else 0

    timezone: int = 0


@dataclass
class NTP(PetlibroMessage):
    """NTP request message."""


@dataclass
class ATTR_SET_SERVICE(PetlibroMessage):
    """Service to set device attributes."""

    coverOpenMode: str = "KEEP_CLOSED"

    def __init__(self, coverOpen: bool | None = None) -> None:
        """Initialize with cover state.

        Args:
            coverOpen: True to open, False to close, None for default
        """
        super().__init__()
        if coverOpen is not None:
            self.coverOpenMode = "KEEP_OPEN" if coverOpen else "KEEP_CLOSED"


@dataclass
class FoodPlan(MQTTMessage):
    """Single feeding plan."""

    grainNum: int = 0
    executionTime: str = ""
    planId: int | None = None
    enableAudio: bool = False
    audioTimes: int = 0
    syncTime: int = 0


@dataclass
class FEEDING_PLAN_SERVICE(PetlibroMessage):
    """Feeding plan service message."""

    plans: list[FoodPlan] = field(default_factory=list)

    def add_plan(self, plan: FoodPlan) -> None:
        """Add a feeding plan.

        Args:
            plan: The feeding plan to add
        """
        if plan.planId is None:
            # Plan IDs start at 1, not 0
            plan.planId = len(self.plans) + 1
        self.plans.append(plan)

    def remove_plan(self, index: int) -> FoodPlan:
        """Remove a feeding plan by index.

        Args:
            index: The index of the plan to remove

        Returns:
            The removed feeding plan

        Raises:
            IndexError: If index is out of range
        """
        return self.plans.pop(index)

    def update_plan(self, plan: FoodPlan) -> None:
        """Update an existing feeding plan.

        Args:
            plan: The feeding plan to update (must have planId set)

        Raises:
            ValueError: If plan has no planId
            IndexError: If planId is invalid
        """
        if plan.planId is None:
            msg = "Plan ID must be set for update"
            raise ValueError(msg)

        # Find and update the plan
        for i, existing_plan in enumerate(self.plans):
            if existing_plan.planId == plan.planId:
                self.plans[i] = plan
                return

        msg = f"Plan with ID {plan.planId} not found"
        raise IndexError(msg)

    def from_mqtt_payload(self, payload: dict[str, Any]) -> FEEDING_PLAN_SERVICE:
        """Deserialize feeding plan service from payload.

        Args:
            payload: The payload dictionary

        Returns:
            Self with updated attributes
        """
        # Handle plans list specially
        plans_data = payload.get("plans", [])
        if plans_data:
            self.plans = []
            for plan_dict in plans_data:
                plan = FoodPlan()
                plan.from_mqtt_payload(plan_dict)
                self.plans.append(plan)

        # Handle other fields
        for key, value in payload.items():
            if key != "plans" and hasattr(self, key):
                setattr(self, key, value)

        return self


@dataclass
class DEVICE_FEEDING_PLAN_SERVICE(PetlibroMessage):
    """Request feeding plan from device."""
