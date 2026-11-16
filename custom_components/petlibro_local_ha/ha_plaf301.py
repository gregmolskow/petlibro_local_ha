"""PLAF301 Petlibro feeder device handler."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback

from .ha_petlibro_base import PetlibroDeviceBase
from .plaf301_const import (
    ERROR_CLOGGED,
    ERROR_EMPTY,
    ERROR_NONE,
    ERROR_UNKNOWN,
    FeederState,
)
from .plaf301_message_data import (
    ATTR_PUSH_EVENT,
    ATTR_SET_SERVICE,
    DEVICE_FEEDING_PLAN_SERVICE,
    FEEDING_PLAN_SERVICE,
    MANUAL_FEEDING_SERVICE,
    FoodPlan,
)
from .shared_const import (
    _LOGGER,
    MODEL_PLAF301,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from paho.mqtt.client import MQTTMessage


class PLAF301(PetlibroDeviceBase):
    """MQTT-enabled Petlibro PLAF301 feeder."""

    def __init__(
        self,
        hass: HomeAssistant,
        serial_number: str,
        name: str,
    ) -> None:
        """Initialize the feeder.

        Args:
            hass: Home Assistant instance
            serial_number: Device serial number
            name: Friendly name for the device
        """
        super().__init__(hass, serial_number, name, MODEL_PLAF301)

        # Feeder-specific state tracking
        self._current_state: ATTR_PUSH_EVENT = ATTR_PUSH_EVENT()
        self._schedule: FEEDING_PLAN_SERVICE = FEEDING_PLAN_SERVICE()
        self._is_dispensing = False

        # Door transition tracking
        self._door_is_opening = False
        self._door_is_closing = False
        self._door_transition_timer = None

    # ==================== Feeder-Specific Properties ====================

    @property
    def is_door_open(self) -> bool:
        """Check if the barn door is open."""
        return self._current_state.barnDoorState or False

    @property
    def is_door_opening(self) -> bool:
        """Check if door is currently opening."""
        return self._door_is_opening

    @property
    def is_door_closing(self) -> bool:
        """Check if door is currently closing."""
        return self._door_is_closing

    @property
    def is_clogged(self) -> bool:
        """Check if the grain outlet is clogged."""
        return not self._current_state.grainOutletState

    @property
    def is_dispensing(self) -> bool:
        """Check if currently dispensing food."""
        return self._is_dispensing

    @property
    def is_empty(self) -> bool:
        """Check if grain storage is empty."""
        return not self._current_state.surplusGrain

    @property
    def current_state(self) -> FeederState:
        """Get the current state of the device."""
        if self.is_empty:
            return FeederState.ERROR
        if self.is_clogged:
            return FeederState.ERROR
        if self.is_dispensing:
            return FeederState.DISPENSING
        if self.is_door_open:
            return FeederState.DOOR_OPEN
        if not self.is_door_open:
            return FeederState.DOOR_CLOSED
        return FeederState.UNKNOWN

    @property
    def error_code(self) -> str:
        """Get current error code."""
        if self.is_empty:
            return ERROR_EMPTY
        if self.is_clogged:
            return ERROR_CLOGGED
        if self.current_state == FeederState.ERROR:
            return ERROR_UNKNOWN
        return ERROR_NONE

    @property
    def feeding_schedule(self) -> dict[str, Any]:
        """Get the current feeding schedule."""
        return self._schedule.to_dict()

    # ==================== State Management ====================

    def get_state_dict(self) -> dict[str, Any]:
        """Get state as dictionary for coordinator.

        Returns:
            dict: Current device state
        """
        return {
            "state": self.current_state,
            "activity": self.current_state.to_ha_activity(),
            "is_door_open": self.is_door_open,
            "is_door_opening": self.is_door_opening,
            "is_door_closing": self.is_door_closing,
            "is_dispensing": self.is_dispensing,
            "is_empty": self.is_empty,
            "is_clogged": self.is_clogged,
            "error_code": self.error_code,
            "rssi": self._heartbeat.rssi,
            "is_online": self.is_online,
            "last_seen": self.last_seen,
            "seconds_since_heartbeat": self.seconds_since_last_heartbeat,
            "feeding_schedule": self.feeding_schedule,
            "feeding_plans": self.feeding_schedule.get("plans", []),
        }

    # ==================== MQTT Message Handlers ====================

    @callback
    def _handle_event_message(self, msg: MQTTMessage) -> None:
        """Handle incoming event messages for feeder.

        Args:
            msg: MQTT message received
        """
        try:
            payload: dict = json.loads(msg.payload)
            cmd = payload.get("cmd")
            update: bool = True

            if cmd == "ATTR_PUSH_EVENT":
                self._current_state.from_mqtt_payload(payload)
                _LOGGER.debug(
                    "Updated feeder attributes: barnDoor=%s, surplusGrain=%s, grainOutlet=%s",
                    self._current_state.barnDoorState,
                    self._current_state.surplusGrain,
                    self._current_state.grainOutletState,
                )

            elif cmd == "DEVICE_START_EVENT":
                self._startup_info.from_mqtt_payload(payload)
                _LOGGER.info(
                    "Feeder started: %s", self._startup_info.softwareVersion
                )

            elif cmd == "WAREHOUSE_DOOR_EVENT":
                self._handle_door_event(payload)

            elif cmd == "GRAIN_OUTPUT_EVENT":
                finished = payload.get("finished", True)
                self._is_dispensing = not finished
                _LOGGER.debug("Dispensing: %s", self._is_dispensing)

                # Acknowledge grain output event on event/sub
                ack_payload = {
                    "cmd": "GRAIN_OUTPUT_EVENT",
                    "ts": int(time.time() * 1000),
                    "msgId": payload.get("msgId", ""),
                    "code": 0,
                    "execStep": payload.get("execStep", ""),
                }
                self.hass.async_create_task(
                    self._publish_event_reply(ack_payload)
                )

            elif cmd == "GET_FEEDING_PLAN_EVENT":
                _LOGGER.info(
                    "Feeder requested feeding plans (GET_FEEDING_PLAN_EVENT)"
                )
                clean_plans = [
                    p.to_dict() if hasattr(p, "to_dict") else p
                    for p in self._schedule.plans
                ]
                reply_payload = {
                    "cmd": "GET_FEEDING_PLAN_EVENT",
                    "code": 0,
                    "ts": int(time.time() * 1000),
                    "msgId": payload.get("msgId", ""),
                    "plans": clean_plans,
                }
                self.hass.async_create_task(
                    self._publish_event_reply(reply_payload)
                )

            else:
                _LOGGER.warning("Unknown feeder event command: %s", cmd)
                update = False

            # Notify callback of state change
            if self._state_change_callback and update:
                _LOGGER.debug("Updating values from feeder state change")
                self.hass.async_create_task(self._state_change_callback())

        except Exception as err:
            _LOGGER.exception("Error handling feeder event message: %s", err)

    # ==================== Event Handlers ====================

    def _handle_door_event(self, payload: dict) -> None:
        """Handle warehouse door event.

        Args:
            payload: Event payload
        """
        door_state = payload.get("barnDoorState", False)
        trigger_type = payload.get("triggerType", "")

        _LOGGER.debug(
            "Door event: state=%s, trigger=%s, current_state=%s",
            door_state,
            trigger_type,
            self._current_state.barnDoorState,
        )

        # Determine if door is transitioning
        old_state = self._current_state.barnDoorState
        new_state = door_state

        # Clear any existing transition timer
        if self._door_transition_timer:
            self._door_transition_timer.cancel()
            self._door_transition_timer = None

        if old_state != new_state:
            # Door state is changing
            if new_state:
                # Door is opening
                self._door_is_opening = True
                self._door_is_closing = False
                _LOGGER.debug("Door is opening")
            else:
                # Door is closing
                self._door_is_opening = False
                self._door_is_closing = True
                _LOGGER.debug("Door is closing")

            # Set a timer to clear the transition state after 5 seconds
            # (in case we don't get a final state update)
            self._door_transition_timer = self.hass.loop.call_later(
                5.0, self._clear_door_transition
            )
        else:
            # Door has reached its final position
            self._door_is_opening = False
            self._door_is_closing = False
            _LOGGER.debug("Door reached final position")

        self._current_state.barnDoorState = door_state
        _LOGGER.debug("Door state changed: %s", door_state)

    def _clear_door_transition(self) -> None:
        """Clear door transition flags (called by timer)."""
        _LOGGER.debug("Clearing door transition state (timeout)")
        self._door_is_opening = False
        self._door_is_closing = False
        self._door_transition_timer = None

        # Notify callback of state change
        if self._state_change_callback:
            self.hass.async_create_task(self._state_change_callback())

    def _handle_device_specific_control_response(
        self, cmd: str, payload: dict
    ) -> bool:
        """Handle feeder-specific control responses.

        Args:
            cmd: Command name from the response
            payload: Full response payload

        Returns:
            bool: True if response was handled
        """
        if cmd in ("DEVICE_FEEDING_PLAN_SERVICE", "FEEDING_PLAN_SERVICE"):
            code = payload.get("code", 0)
            if code == 0:
                self._schedule.from_mqtt_payload(payload)
                _LOGGER.info(
                    "Updated feeding schedule: %s", self._schedule.to_dict()
                )
            else:
                _LOGGER.warning(
                    "Feeding plan response error code: %s", code
                )
            return True

        if cmd in ("MANUAL_FEEDING_SERVICE", "SWITCH_DOOR_SERVICE"):
            _LOGGER.debug("%s ack received: code=%s", cmd, payload.get("code"))
            return True

        return False

    # ==================== Lifecycle ====================

    async def _device_specific_start(self) -> None:
        """Perform feeder-specific initialization."""
        # Request feeding schedule
        await self.request_feeding_schedule()

    async def _device_specific_cleanup(self) -> None:
        """Perform feeder-specific cleanup."""
        # Cancel door transition timer if active
        if self._door_transition_timer:
            self._door_transition_timer.cancel()
            self._door_transition_timer = None

    # ==================== Feeder Commands ====================

    async def open_door(self) -> None:
        """Open the barn door."""
        _LOGGER.info("Opening barn door")
        self._door_is_opening = True
        self._door_is_closing = False
        await self._publish_command(ATTR_SET_SERVICE(coverOpen=True))

        # Notify callback of state change
        await self._notify_state_change()

    async def close_door(self) -> None:
        """Close the barn door."""
        _LOGGER.info("Closing barn door")
        self._door_is_closing = True
        self._door_is_opening = False
        await self._publish_command(ATTR_SET_SERVICE(coverOpen=False))

        # Notify callback of state change
        await self._notify_state_change()

    async def toggle_door(self) -> None:
        """Toggle the barn door state."""
        if self.is_door_open:
            await self.close_door()
        else:
            await self.open_door()

    async def dispense_food(self, amount: int = 1) -> None:
        """Dispense food.

        Args:
            amount: Number of portions to dispense (default: 1)
        """
        if amount < 1:
            _LOGGER.warning("Invalid dispense amount: %s", amount)
            return

        _LOGGER.info("Dispensing %s portion(s)", amount)
        msg = MANUAL_FEEDING_SERVICE()
        msg.grainNum = amount
        await self._publish_command(msg)

    # ==================== Feeding Schedule Management ====================

    def add_feeding_plan(
        self,
        id: int,
        time: str | int,
        amount: int = 1,
        repeat_day: list[int] | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a feeding plan to the device.

        Args:
            id: Plan ID
            time: Execution time
            amount: Number of grain portions
            repeat_day: List of days (1=Mon..7=Sun)
            **kwargs: Extra keyword arguments for compatibility
        """
        if "executionTime" in kwargs:
            time = kwargs["executionTime"]
        if "grainNum" in kwargs:
            amount = kwargs["grainNum"]

        if repeat_day is None:
            repeat_day = [1, 2, 3, 4, 5, 6, 7]

        tmp = FoodPlan(
            grainNum=amount,
            executionTime=str(time),
            planId=id,
            repeatDay=repeat_day,
        )
        self._schedule.add_plan(tmp)

    async def request_feeding_schedule(self) -> None:
        """Request the current feeding schedule from the device."""
        _LOGGER.debug("Requesting feeding plan update")
        tmp = self._schedule.ts
        await self._publish_command(DEVICE_FEEDING_PLAN_SERVICE())

        max_attempts = 30  # 30 * 0.3 = 9 seconds
        attempts = 0

        while self._schedule.ts == tmp and attempts < max_attempts:
            await asyncio.sleep(0.3)
            attempts += 1

            # Retry command every 3 seconds
            if attempts % 10 == 0:
                _LOGGER.debug(
                    "Retrying feeding schedule request (attempt %d)",
                    attempts // 10,
                )
                await self._publish_command(DEVICE_FEEDING_PLAN_SERVICE())

        if attempts >= max_attempts:
            _LOGGER.warning("Timeout waiting for feeding schedule update")
        else:
            _LOGGER.debug(
                "Feeding schedule updated after %d attempts", attempts
            )

    async def update_feeding_plan_service(
        self, feeding_plan: FEEDING_PLAN_SERVICE
    ) -> None:
        """Update and publish the feeding plan on the device.

        Args:
            feeding_plan: Feeding plan to set
        """
        _LOGGER.debug(
            f"Setting feeding plan on device from {self._schedule.to_dict()}"
        )
        self._schedule.plans = []
        for idx, plan in enumerate(feeding_plan.plans, start=1):
            # Ensure plan has proper ID
            if plan.planId is None:
                plan.planId = idx
            _LOGGER.debug(f"    adding plan: {plan.to_dict()}")
            self._schedule.plans.append(plan)

        self._schedule.ts = int(time.time() * 1000)
        self._schedule.msgId = f"{self._sn}_{int(time.time())}"
        await self._publish_command(self._schedule)
