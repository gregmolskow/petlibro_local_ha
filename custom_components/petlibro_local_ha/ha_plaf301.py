"""PLAF301 Petlibro feeder device handler."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from homeassistant.components import mqtt
from homeassistant.core import callback

from .const import (
    _LOGGER,
    ERROR_CLOGGED,
    ERROR_EMPTY,
    ERROR_NONE,
    ERROR_UNKNOWN,
    MANUFACTURER,
    MODEL_PLAF301,
    TOPIC_DEVICE_CONTROL,
    TOPIC_DEVICE_CONTROL_IN,
    TOPIC_DEVICE_EVENT,
    TOPIC_DEVICE_HEARTBEAT,
    FeederState,
)
from .message_data import (
    ATTR_PUSH_EVENT,
    ATTR_SET_SERVICE,
    DEVICE_FEEDING_PLAN_SERVICE,
    DEVICE_START_EVENT,
    FEEDING_PLAN_SERVICE,
    HEARTBEAT,
    MANUAL_FEEDING_SERVICE,
    NTP,
    NTP_SYNC,
    FoodPlan,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from paho.mqtt.client import MQTTMessage


class PLAF301:
    """MQTT-enabled Petlibro PLAF301 feeder."""

    HEARTBEAT_TIMEOUT = 300
    """The maximum allowed time (in seconds) between heartbeats before considering the device offline."""

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
        self.hass = hass
        self._sn = serial_number.upper()
        self._name = name
        self._model = MODEL_PLAF301

        # State tracking
        self._current_state: ATTR_PUSH_EVENT = ATTR_PUSH_EVENT()
        self._startup_info: DEVICE_START_EVENT = DEVICE_START_EVENT()
        self._heartbeat: HEARTBEAT = HEARTBEAT()
        self._schedule: FEEDING_PLAN_SERVICE = FEEDING_PLAN_SERVICE()

        self._is_dispensing = False
        self._last_heartbeat: float = 0
        self._last_heartbeat_time: float = time.time()

        # MQTT unsubscribe functions
        self._unsub_funcs: list = []

        # Callback for state changes
        self._state_change_callback: callable | None = None

    def set_state_change_callback(self, callback: callable) -> None:
        """Set callback to be called when state changes.

        Args:
            callback: Function to call on state change
        """
        self._state_change_callback = callback

    @property
    def serial_number(self) -> str:
        """Return device serial number."""
        return self._sn

    @property
    def name(self) -> str:
        """Return device name."""
        return self._name

    @property
    def model(self) -> str:
        """Return device model."""
        return self._model

    @property
    def manufacturer(self) -> str:
        """Return device manufacturer."""
        return MANUFACTURER

    # MQTT Topics
    def _get_topic(self, topic_template: str) -> str:
        """Format topic with model and serial number."""
        return topic_template.format(model=self._model, sn=self._sn)

    @property
    def event_topic(self) -> str:
        """Topic for receiving events."""
        return self._get_topic(TOPIC_DEVICE_EVENT)

    @property
    def control_topic(self) -> str:
        """Topic for sending control commands."""
        return self._get_topic(TOPIC_DEVICE_CONTROL)

    @property
    def control_in_topic(self) -> str:
        """Topic for receiving control responses."""
        return self._get_topic(TOPIC_DEVICE_CONTROL_IN)

    @property
    def heartbeat_topic(self) -> str:
        """Topic for receiving heartbeat messages."""
        return self._get_topic(TOPIC_DEVICE_HEARTBEAT)

    # State Properties
    @property
    def is_door_open(self) -> bool:
        """Check if the barn door is open."""
        return self._current_state.barnDoorState or False

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
    def is_online(self) -> bool:
        """Check if device is online based on heartbeat."""
        if self._last_heartbeat_time == 0:
            return False

        time_since_heartbeat = time.time() - self._last_heartbeat_time
        return time_since_heartbeat < self.HEARTBEAT_TIMEOUT

    @property
    def last_seen(self) -> float:
        """Return timestamp of last heartbeat."""
        return self._last_heartbeat_time

    @property
    def seconds_since_last_heartbeat(self) -> int:
        """Return seconds since last heartbeat."""
        if self._last_heartbeat_time == 0:
            return -1
        return int(time.time() - self._last_heartbeat_time)

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

    def get_state_dict(self) -> dict[str, Any]:
        """Get state as dictionary for coordinator.

        Returns:
            dict: Current device state
        """
        return {
            "state": self.current_state,
            "activity": self.current_state.to_ha_activity(),
            "is_door_open": self.is_door_open,
            "is_dispensing": self.is_dispensing,
            "is_empty": self.is_empty,
            "is_clogged": self.is_clogged,
            "error_code": self.error_code,
            "rssi": self._heartbeat.rssi,
            "is_online": self.is_online,  # Add this
            "last_seen": self.last_seen,  # Add this
            "seconds_since_heartbeat": self.seconds_since_last_heartbeat,  # Add this
        }

    def add_feeding_plan(
        self,
        id,
        time: int,
        amount: int,
    ) -> None:
        """Add a feeding plan to the device."""
        tmp = FoodPlan(
            grainNum=amount,
            executionTime=time,
            planId=id,
        )
        self._schedule.add_plan(tmp)

    async def start(self) -> None:
        """Start the device handler and subscribe to MQTT topics."""
        _LOGGER.info("Starting PLAF301 device: %s", self._sn)

        try:
            # Subscribe to event topic
            unsub = await mqtt.async_subscribe(
                self.hass,
                self.event_topic,
                self._handle_event_message,
                encoding="utf-8",
            )
            self._unsub_funcs.append(unsub)

            # Subscribe to heartbeat topic
            unsub = await mqtt.async_subscribe(
                self.hass,
                self.heartbeat_topic,
                self._handle_heartbeat_message,
                encoding="utf-8",
            )
            self._unsub_funcs.append(unsub)

            # Subscribe to control response topic
            unsub = await mqtt.async_subscribe(
                self.hass,
                self.control_in_topic,
                self._handle_control_response,
                encoding="utf-8",
            )
            self._unsub_funcs.append(unsub)

            # Sync time with device
            await self.sync_time()

            # Request feeding schedule
            await self.request_feeding_schedule()

            _LOGGER.info("Successfully started PLAF301 device: %s", self._sn)

        except Exception as err:
            _LOGGER.exception("Failed to start PLAF301 device: %s", err)
            raise

    async def cleanup(self) -> None:
        """Clean up resources."""
        _LOGGER.info("Cleaning up PLAF301 device: %s", self._sn)

        # Unsubscribe from MQTT topics
        for unsub in self._unsub_funcs:
            unsub()
        self._unsub_funcs.clear()

    @callback
    def _handle_event_message(self, msg: MQTTMessage) -> None:
        """Handle incoming event messages.

        Args:
            msg: MQTT message received
        """
        try:
            payload: dict = json.loads(msg.payload)
            cmd = payload.get("cmd")

            update: bool = True

            if cmd == "ATTR_PUSH_EVENT":
                self._current_state.from_mqtt_payload(payload)
                _LOGGER.debug("Updated device attributes")

            elif cmd == "DEVICE_START_EVENT":
                self._startup_info.from_mqtt_payload(payload)
                _LOGGER.info(
                    "Device started: %s", self._startup_info.softwareVersion
                )

            elif cmd == "WAREHOUSE_DOOR_EVENT":
                door_state = payload.get("barnDoorState", False)
                self._current_state.barnDoorState = door_state
                _LOGGER.debug("Door state changed: %s", door_state)

            elif cmd == "GRAIN_OUTPUT_EVENT":
                finished = payload.get("finished", True)
                self._is_dispensing = not finished
                _LOGGER.debug("Dispensing: %s", self._is_dispensing)

            else:
                _LOGGER.warning("Unknown event command: %s", cmd)
                update = False

            # Notify callback of state change
            if self._state_change_callback and update:
                _LOGGER.debug("Updating values from state change")
                self.hass.async_create_task(self._state_change_callback())

        except Exception as err:
            _LOGGER.exception("Error handling event message: %s", err)

    @callback
    def _handle_heartbeat_message(self, msg: MQTTMessage) -> None:
        """Handle incoming heartbeat messages.

        Args:
            msg: MQTT message received
        """
        try:
            payload: dict = json.loads(msg.payload)
            self._last_heartbeat = payload.get("ts")
            self._last_heartbeat_time = time.time()
            self._heartbeat.from_mqtt_payload(payload)
            _LOGGER.debug(
                "Received heartbeat(%s): RSSI=%s",
                self._heartbeat.ts,
                self._heartbeat.rssi,
            )

            # Trigger state update since device is online
            if self._state_change_callback:
                self.hass.async_create_task(self._state_change_callback())

        except Exception as err:
            _LOGGER.exception("Error handling heartbeat message: %s", err)

    @callback
    def _handle_control_response(self, msg: MQTTMessage) -> None:
        """Handle incoming control response messages.

        Args:
            msg: MQTT message received
        """
        try:
            payload: dict = json.loads(msg.payload)
            cmd = payload.get("cmd")

            _LOGGER.info("Received control response: %s", payload)
            if cmd == "DEVICE_FEEDING_PLAN_SERVICE":
                self._schedule.from_mqtt_payload(payload)
                _LOGGER.info(
                    f"Updated feeding schedule {self._schedule.to_dict()}"
                )
            else:
                _LOGGER.warning("Unknown control response: %s", cmd)

        except Exception as err:
            _LOGGER.exception("Error handling control response: %s", err)

    async def _publish_command(self, message: MQTTMessage) -> None:
        """Publish a command to the device.

        Args:
            message: Message object to publish
        """
        try:
            payload = message.to_mqtt_payload()
            await mqtt.async_publish(
                self.hass,
                self.control_topic,
                payload,
                qos=1,
            )
            _LOGGER.debug(
                "Published command: %s to topic %s",
                message.cmd,
                self.control_topic,
            )

        except Exception as err:
            _LOGGER.exception("Error publishing command: %s", err)
            raise

    async def sync_time(self) -> None:
        """Synchronize time with the device."""
        _LOGGER.debug("Syncing time with device")
        # tmp = self._current_state.ts
        await self._publish_command(NTP_SYNC())
        # while self._current_state.ts == tmp:
        await asyncio.sleep(0.3)
        #     _LOGGER.debug("NTP New TS %s, saved %s", self._schedule.ts, tmp)
        # _LOGGER.debug("Feeding Plan update done")

    async def request_feeding_schedule(self) -> None:
        """Request the current feeding schedule from the device."""
        _LOGGER.debug("Requesting feeding plan update")
        tmp = self._schedule.ts
        await self._publish_command(DEVICE_FEEDING_PLAN_SERVICE())
        while self._schedule.ts == tmp:
            await asyncio.sleep(0.3)
            await self._publish_command(DEVICE_FEEDING_PLAN_SERVICE())
        _LOGGER.debug("Feeding Plan update done")

    async def request_state_update(self) -> None:
        """Request current state from the device."""
        _LOGGER.debug("Requesting state update")
        tmp = self._heartbeat.ts
        await self._publish_command(NTP())
        while self._heartbeat.ts == tmp:
            await asyncio.sleep(0.1)
        _LOGGER.debug("State update done")

    async def open_door(self) -> None:
        """Open the barn door."""
        _LOGGER.info("Opening barn door")
        await self._publish_command(ATTR_SET_SERVICE(coverOpen=True))

    async def close_door(self) -> None:
        """Close the barn door."""
        _LOGGER.info("Closing barn door")
        await self._publish_command(ATTR_SET_SERVICE(coverOpen=False))

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
        # for plan in feeding_plan.plans:
        #     _LOGGER.debug(f"    new plan: {plan.to_dict()}")
        #     self._schedule.update_plan(plan)
        # _LOGGER.debug(f"Updated schedule: {self._schedule.to_dict()}")
        tmp = self._schedule
        # tmp.cmd = "DEVICE_FEEDING_PLAN_SERVICE"
        await self._publish_command(tmp)
