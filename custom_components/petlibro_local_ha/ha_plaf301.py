import asyncio
import json

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from paho.mqtt.client import MQTTMessage

from .const import (
    State,
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
)


class PLAF301:  # noqa: PLR0904
    """MQTT-enabled robot vacuum for HA."""

    _model: str = "PLAF301"
    """The model fo the device"""
    _manufacturer: str = "Petlibro"
    """The device manufacturer"""
    _sn: str | None = None
    """The device serial number"""

    _startup_info: DEVICE_START_EVENT = DEVICE_START_EVENT()
    """Startup information of the device"""
    _current_state: ATTR_PUSH_EVENT = ATTR_PUSH_EVENT()
    """Current state of the device"""
    _schedule: FEEDING_PLAN_SERVICE = FEEDING_PLAN_SERVICE()
    """Feeding schedule of the device"""
    _state: State = State(State.UNKNOWN)
    """External state of the device"""
    _is_on: bool = False
    """Power state of the device"""
    _heartbeat: HEARTBEAT = HEARTBEAT()
    """Heartbeat information of the device"""

    def __init__(
        self,
        hass: HomeAssistant,
        sn: str,
        name: str,
    ) -> None:
        """Initialize the vacuum entity."""
        self.hass = hass
        self._sn = sn.upper()

        self._dispensing_: bool | None = None
        self.timestamp: int | None = None

    async def start(self) -> None:
        """Start the vacuum entity and subscribe to MQTT topics."""
        await mqtt.async_subscribe(
            self.hass,
            self.cat_feeder_event_topic,
            self._mqtt_command_received,
            encoding="json",
        )

        await mqtt.async_subscribe(
            self.hass,
            self.cat_feeder_heartbeat_topic,
            self._mqtt_command_received,
            encoding="json",
        )

        await self.async_sync_time()

        await self.open_cover()

        await asyncio.sleep(10)

        await self.close_cover()

    # Define the PetLibro MQTT topics
    @property
    def cat_feeder_event_topic(self) -> str:
        """Topic for receiving events from the cat feeder."""
        return f"dl/{self._model}/{self._sn}/device/event/post"

    @property
    def cat_feeder_control_topic(self) -> str:
        """Topic for sending control commands to the cat feeder."""
        return f"dl/{self._model}/{self._sn}/device/service/sub"

    @property
    def cat_feeder_control_in_topic(self) -> str:
        """Topic for receiving control commands from the cat feeder."""
        return f"dl/{self._model}/{self._sn}/device/service/post"

    @property
    def cat_feeder_heartbeat_topic(self) -> str:
        """Topic for receiving heartbeat messages from the cat feeder."""
        return f"dl/{self._model}/{self._sn}/device/heart/post"

    @property
    def is_open(self) -> bool | None:
        """Check if the barn door is open."""
        return self._current_state.barnDoorState

    @property
    def is_clogged(self) -> bool:
        """Check if the grain outlet is clogged."""
        return not self._current_state.grainOutletState

    @property
    def dispensing(self) -> bool | None:
        """Check if the device is currently dispensing food."""
        return self._dispensing_

    @property
    def is_empty(self) -> bool:
        """Check if the grain storage is empty."""
        return not self._current_state.surplusGrain

    @property
    def is_on(self) -> bool:
        return self._is_on

    # Define the HA error status topics
    @property
    def ha_error_topic(self) -> str:
        """Topic for receiving error codes from Home Assistant."""
        return f"dl/{self._model}/{self._sn}/ha/errorcode"

    @property
    def ha_heartbeat_topic(self) -> str:
        """Topic for receiving heartbeat messages from Home Assistant."""
        return f"dl/{self._model}/{self._sn}/ha/heartbeat"

    async def async_sync_time(self) -> None:
        """Synchronize the time with the device."""
        msgout = NTP_SYNC()
        await mqtt.async_publish(
            self.hass,
            self.cat_feeder_control_topic,
            msgout.to_mqtt_payload(),
        )

    async def update_state(self) -> None:
        """Request the current state of the device."""
        msgout = NTP()
        await mqtt.async_publish(
            self.hass,
            self.cat_feeder_control_topic,
            msgout.to_mqtt_payload(),
        )

    async def async_publish_discovery(self) -> None:
        """Publish MQTT discovery payload so HA auto-adds the error state."""
        error_payload = {
            "name": f"{self.name} Error Code",
            "unique_id": f"{self._sn}_error",
            "state_topic": self.ha_error_topic,
            "availability_topic": self.ha_heartbeat_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "expire_after": 300,
        }

        await mqtt.async_publish(
            self.hass,
            self.ha_error_topic,
            json.dumps(error_payload),
            qos=1,
            retain=True,
        )

    @callback
    def _mqtt_command_received(self, msg: MQTTMessage) -> None:
        """Define the callback function to handle incoming MQTT messages.

        :param msg: The MQTT message received.
        :type msg: mqtt.MQTTMessage
        """
        # Process the message
        payload: dict = json.loads(msg.payload)
        if msg.topic == self.cat_feeder_heartbeat_topic:
            self.timestamp = payload.get("ts")
            self._heartbeat.from_mqtt_payload(payload)

        elif msg.topic == self.cat_feeder_event_topic:
            if payload.get("cmd") == "ATTR_PUSH_EVENT":
                self._current_state.from_mqtt_payload(payload)
            elif payload.get("cmd") == "DEVICE_START_EVENT":
                self._startup_info.from_mqtt_payload(payload)
            elif payload.get("cmd") == "WAREHOUSE_DOOR_EVENT":
                self._current_state.barnDoorState = payload.get("barnDoorState")
            elif payload.get("cmd") == "GRAIN_OUTPUT_EVENT":
                self._dispensing_ = not payload.get("finished")

        elif msg.topic == self.cat_feeder_control_in_topic:
            if payload.get("cmd") == "DEVICE_FEEDING_PLAN_SERVICE":
                self._schedule.from_mqtt_payload(payload)

        # Update the error mqtt topic
        if self._state == State.ERROR:
            error = "UNKNOWN"
            if self.is_empty:
                error = "EMPTY"
            elif self.is_clogged:
                error = "CLOGGED"
            mqtt.async_publish(self.hass, self.ha_error_topic, error)
        else:
            mqtt.async_publish(self.hass, self.ha_error_topic, "none")

    async def open_cover(self) -> None:
        """Open the cover of the cat feeder."""
        msgout = ATTR_SET_SERVICE(coverOpen=True)
        await mqtt.async_publish(
            self.hass,
            self.cat_feeder_control_topic,
            msgout.to_mqtt_payload(),
        )
        await self.update_state()

    async def close_cover(self) -> None:
        """Close the cover of the cat feeder."""
        msgout = ATTR_SET_SERVICE(coverOpen=False)
        await mqtt.async_publish(
            self.hass,
            self.cat_feeder_control_topic,
            msgout.to_mqtt_payload(),
        )
        await self.update_state()

    async def toggle_cover(self, **kwargs: dict) -> None:
        """Toggle the cover state."""
        self._is_on = False
        if self.is_open:
            await self.close_cover()
        else:
            await self.open_cover()

    @property
    def status(self) -> str:
        """Get the current status of the device."""
        if self.is_empty:
            self._state = State.ERROR
        elif self.dispensing:
            self._state = State.DISPENSING
        elif not self.is_open:
            self._state = State.DOOR_CLOSED
        elif self.is_open:
            self._state = State.DOOR_OPEN
        else:
            self._state = State.ERROR
        return self._state.toHA()

    async def dispense_food(self, amount: int) -> None:
        """Dispense a specified amount of food from the cat feeder.

        :param amount: The amount of food to dispense.
        :type amount: int
        """
        msgout = MANUAL_FEEDING_SERVICE()
        msgout.grainNum = amount
        await mqtt.async_publish(
            self.hass,
            self.cat_feeder_control_topic,
            msgout.to_mqtt_payload(),
        )
        await self.update_state()
