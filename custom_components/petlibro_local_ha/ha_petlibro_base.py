"""Base class for Petlibro MQTT devices."""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from homeassistant.components import mqtt
from homeassistant.core import callback

from .message_data import (
    ATTR_PUSH_EVENT,
    DEVICE_START_EVENT,
    HEARTBEAT,
    NTP,
    NTP_SYNC,
)
from .shared_const import (
    _LOGGER,
    MANUFACTURER,
    TOPIC_DEVICE_CONTROL,
    TOPIC_DEVICE_CONTROL_IN,
    TOPIC_DEVICE_EVENT,
    TOPIC_DEVICE_HEARTBEAT,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from paho.mqtt.client import MQTTMessage


class PetlibroDeviceBase(ABC):
    """Base class for MQTT-enabled Petlibro devices."""

    HEARTBEAT_TIMEOUT = 300
    """The maximum allowed time (in seconds) between heartbeats before considering the device offline."""

    def __init__(
        self,
        hass: HomeAssistant,
        serial_number: str,
        name: str,
        model: str,
    ) -> None:
        """Initialize the device.

        Args:
            hass: Home Assistant instance
            serial_number: Device serial number
            name: Friendly name for the device
            model: Device model identifier
        """
        self.hass = hass
        self._sn = serial_number.upper()
        self._name = name
        self._model = model

        # State tracking - common to all devices
        self._current_state: ATTR_PUSH_EVENT = ATTR_PUSH_EVENT()
        self._startup_info: DEVICE_START_EVENT = DEVICE_START_EVENT()
        self._heartbeat: HEARTBEAT = HEARTBEAT()

        self._last_heartbeat: float = 0
        self._last_heartbeat_time: float = time.time()

        # MQTT unsubscribe functions
        self._unsub_funcs: list = []

        # Callback for state changes
        self._state_change_callback: callable | None = None

    # ==================== Properties ====================

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

    # ==================== MQTT Topics ====================

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

    # ==================== Callback Management ====================

    def set_state_change_callback(self, callback: callable) -> None:
        """Set callback to be called when state changes.

        Args:
            callback: Function to call on state change
        """
        self._state_change_callback = callback

    async def _notify_state_change(self) -> None:
        """Notify callback of state change if set."""
        if self._state_change_callback:
            _LOGGER.debug("Notifying state change callback")
            await self._state_change_callback()

    # ==================== Lifecycle Methods ====================

    async def start(self) -> None:
        """Start the device handler and subscribe to MQTT topics."""
        _LOGGER.info("Starting %s device: %s", self._model, self._sn)

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

            # Device-specific initialization
            await self._device_specific_start()

            _LOGGER.info("Successfully started %s device: %s", self._model, self._sn)

        except Exception as err:
            _LOGGER.exception("Failed to start %s device: %s", self._model, err)
            raise

    async def cleanup(self) -> None:
        """Clean up resources."""
        _LOGGER.info("Cleaning up %s device: %s", self._model, self._sn)

        # Device-specific cleanup
        await self._device_specific_cleanup()

        # Unsubscribe from MQTT topics
        for unsub in self._unsub_funcs:
            unsub()
        self._unsub_funcs.clear()

    # ==================== MQTT Message Handlers ====================

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
                _LOGGER.info("Device started: %s", self._startup_info.softwareVersion)

            else:
                # Let subclass handle device-specific events
                update = self._handle_device_specific_event(cmd, payload)
                if not update:
                    _LOGGER.warning("Unknown event command: %s", cmd)

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

            # Let subclass handle device-specific responses
            if not self._handle_device_specific_control_response(cmd, payload):
                _LOGGER.warning("Unknown control response: %s", cmd)

        except Exception as err:
            _LOGGER.exception("Error handling control response: %s", err)

    # ==================== MQTT Commands ====================

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
        await self._publish_command(NTP_SYNC())
        await asyncio.sleep(0.3)

    async def request_state_update(self) -> None:
        """Request current state from the device."""
        _LOGGER.debug("Requesting state update")
        tmp = self._heartbeat.ts
        await self._publish_command(NTP())
        while self._heartbeat.ts == tmp:
            await asyncio.sleep(0.1)
        _LOGGER.debug("State update done")

    # ==================== Abstract Methods ====================

    @abstractmethod
    def get_state_dict(self) -> dict[str, Any]:
        """Get state as dictionary for coordinator.

        Returns:
            dict: Current device state
        """

    @abstractmethod
    def _handle_device_specific_event(self, cmd: str, payload: dict) -> bool:
        """Handle device-specific event messages.

        Args:
            cmd: Command name from the event
            payload: Full event payload

        Returns:
            bool: True if event was handled and should trigger update, False otherwise
        """

    @abstractmethod
    def _handle_device_specific_control_response(self, cmd: str, payload: dict) -> bool:
        """Handle device-specific control responses.

        Args:
            cmd: Command name from the response
            payload: Full response payload

        Returns:
            bool: True if response was handled, False otherwise
        """

    @abstractmethod
    async def _device_specific_start(self) -> None:
        """Perform device-specific initialization during start.

        This is called after common MQTT subscriptions are set up.
        """

    @abstractmethod
    async def _device_specific_cleanup(self) -> None:
        """Perform device-specific cleanup.

        This is called before MQTT unsubscriptions during cleanup.
        """
