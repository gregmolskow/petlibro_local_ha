"""MQTT message data structures for Petlibro integration.

This module defines dataclasses for various MQTT messages and events used
by the Petlibro smart feeder integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .message_data import MQTTMessage, PetlibroMessage
from .shared_const import _LOGGER


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
class MANUAL_FEEDING_SERVICE(PetlibroMessage):
    """Manual feeding command."""

    grainNum: int = 1


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
    syncTime: int = field(
        default_factory=lambda: int(
            datetime.now().astimezone().timestamp() * 1000
        )
    )


@dataclass
class FEEDING_PLAN_SERVICE(PetlibroMessage):
    """Feeding plan service message."""

    plans: list[FoodPlan] = field(default_factory=list)

    def add_plan(self, plan: FoodPlan) -> None:
        """Add a feeding plan.

        Args:
            plan: The feeding plan to add
        """
        # if plan.planId is None:
        #     # Plan IDs start at 1, not 0
        #     plan.planId = len(self.plans) + 1
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
        _LOGGER.debug(f"Updating feeding plan: {plan.to_dict()}")
        # if plan.planId is None:
        #     msg = "Plan ID must be set for update"
        #     raise ValueError(msg)

        # Find and update the plan
        for i, existing_plan in enumerate(self.plans):
            _LOGGER.debug(
                f"checking existing {self.plans[i].to_dict()} \n  against {plan.to_dict()}\n"
            )
            if existing_plan.executionTime == plan.executionTime:
                _LOGGER.debug(f"updating plan: {plan.to_dict()}\n")
                self.plans[i].executionTime = str(plan.executionTime)
                self.plans[i].grainNum = plan.grainNum
                self.plans[i].enableAudio = plan.enableAudio
                self.plans[i].audioTimes = plan.audioTimes
                return

        msg = f"Plan with Time {plan.executionTime} not found in {self.plans}"
        raise IndexError(msg)

    def from_mqtt_payload(
        self, payload: dict[str, Any]
    ) -> FEEDING_PLAN_SERVICE:
        """Deserialize feeding plan service from payload.

        Args:
            payload: The payload dictionary

        Returns:
            Self with updated attributes
        """
        # Handle plans list specially
        _LOGGER.debug(
            "Deserializing FEEDING_PLAN_SERVICE from payload: %s", payload
        )
        plans_data = payload.get("plans", [])
        if plans_data:
            self.plans = []
            for plan_dict in plans_data:
                plan = FoodPlan()
                plan.from_mqtt_payload(plan_dict)
                self.plans.append(plan)

        # Handle other fields
        for key, value in payload.items():
            if key not in {"plans", "cmd"} and hasattr(self, key):
                setattr(self, key, value)

        self.ts = payload.get("ts", -1)

        return self


@dataclass
class DEVICE_FEEDING_PLAN_SERVICE(PetlibroMessage):
    """Request feeding plan from device."""
