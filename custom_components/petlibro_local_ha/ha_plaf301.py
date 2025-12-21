"""PLAF301 Petlibro feeder device handler."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components import mqtt
from homeassistant.core import callback

from .const import (
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

_LOGGER = logging.getLogger(__name__)


class PLAF301:  # noqa: PLR0904
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
        self.hass = hass
        self._sn = serial_number.upper()
        self._name = name
        self._model = MODEL_PLAF301

        # State tracking
        self._current_state = ATTR_PUSH_EVENT()
        self._startup_info = DEVICE_START_EVENT()
        self._heartbeat = HEARTBEAT()
        self._schedule = FEEDING_PLAN_SERVICE()

        self._is_dispensing = False
        self._last_heartbeat: float | None = None

        # MQTT unsubscribe functions
        self._unsub_funcs: list = []

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
        return not self._current_state.barnDoorState

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
    def battery_level(self) -> int | None:
        """Return battery level percentage."""
        return self._current_state.electricQuantity

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
            "battery_level": self.battery_level,
            "error_code": self.error_code,
            "last_heartbeat": self._last_heartbeat,
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
                _LOGGER.debug("Unknown event command: %s", cmd)

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
            self._heartbeat.from_mqtt_payload(payload)
            _LOGGER.debug("Received heartbeat: RSSI=%s", self._heartbeat.rssi)

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

            if cmd == "DEVICE_FEEDING_PLAN_SERVICE":
                self._schedule.from_mqtt_payload(payload)
                _LOGGER.debug("Updated feeding schedule")
            else:
                _LOGGER.debug("Unknown control response: %s", cmd)

        except Exception as err:
            _LOGGER.exception("Error handling control response: %s", err)

    async def _publish_command(self, message: Any) -> None:
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
            _LOGGER.debug("Published command: %s", message.cmd)

        except Exception as err:
            _LOGGER.exception("Error publishing command: %s", err)
            raise

    async def sync_time(self) -> None:
        """Synchronize time with the device."""
        _LOGGER.debug("Syncing time with device")
        await self._publish_command(NTP_SYNC())

    async def request_state_update(self) -> None:
        """Request current state from the device."""
        _LOGGER.debug("Requesting state update")
        await self._publish_command(NTP())

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
