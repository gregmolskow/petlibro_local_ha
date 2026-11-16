"""PLWF116 Petlibro water fountain device handler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback

from .ha_petlibro_base import PetlibroDeviceBase
from .plwf116_const import (
    ERROR_NONE,
)
from .plwf116_message_data import (
    ATTR_PUSH_EVENT,
    WATER_CAP_EVENT,
)
from .shared_const import (
    _LOGGER,
    MODEL_PLWF116,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from paho.mqtt.client import MQTTMessage


class PLWF116(PetlibroDeviceBase):
    """MQTT-enabled Petlibro PLWF116 water fountain."""

    def __init__(
        self,
        hass: HomeAssistant,
        serial_number: str,
        name: str,
    ) -> None:
        """Initialize the water fountain.

        Args:
            hass: Home Assistant instance
            serial_number: Device serial number
            name: Friendly name for the device
        """
        super().__init__(hass, serial_number, name, MODEL_PLWF116)

        # Import device-specific message types
        self._attr_state: ATTR_PUSH_EVENT = ATTR_PUSH_EVENT()
        self._water_cap_state: WATER_CAP_EVENT = WATER_CAP_EVENT()

        # Derived state
        self._pump_running = False
        self._light_on = False
        self._needs_filter_replacement = False

    # ==================== Water Fountain Properties ====================

    @property
    def water_weight_percent(self) -> int:
        """Get water level as percentage (0-100)."""
        return self._water_cap_state.weightPercent

    @property
    def water_weight(self) -> int:
        """Get absolute water weight."""
        return self._water_cap_state.weight

    @property
    def is_water_detected(self) -> bool:
        """Check if water is detected by radar sensor."""
        return self._water_cap_state.radarDetected

    @property
    def is_low_water(self) -> bool:
        """Check if water level is low."""
        # You can adjust this threshold based on your needs
        return self.water_weight_percent < 20 or self._attr_state.lowWater == 1  # noqa: PLR2004

    @property
    def filter_next_replacement_timestamp(self) -> int | None:
        """Get timestamp when filter should be replaced."""
        return self._attr_state.filterNextReplacementTimestamp

    @property
    def needs_filter_replacement(self) -> bool:
        """Check if filter needs replacement."""
        return self._attr_state.filterLedSwitch

    @property
    def is_light_enabled(self) -> bool:
        """Check if light is enabled."""
        return self._attr_state.enableLight

    @property
    def is_light_on(self) -> bool:
        """Check if light is currently on."""
        return self._attr_state.lightSwitch

    @property
    def battery_level(self) -> int | None:
        """Get battery level percentage."""
        return self._attr_state.electricQuantity

    @property
    def battery_state(self) -> str:
        """Get battery state description."""
        return self._attr_state.batteryState

    @property
    def current_state(self) -> str:
        """Get the current state of the device."""
        # if self.is_low_water:
        #     return WaterFountainState.ERROR
        # if self.needs_filter_replacement:
        #     return WaterFountainState.WARNING
        # if self.is_online:
        #     return WaterFountainState.IDLE
        # return WaterFountainState.UNKNOWN
        return "TestState"  # Placeholder until states are defined

    @property
    def error_code(self) -> str:
        """Get current error code."""
        # if self.is_low_water:
        #     return ERROR_LOW_WATER
        # if self.needs_filter_replacement:
        #     return ERROR_FILTER_REPLACE
        # if self.current_state == WaterFountainState.ERROR:
        #     return ERROR_UNKNOWN
        return ERROR_NONE

    # ==================== State Management ====================

    def get_state_dict(self) -> dict[str, Any]:
        """Get state as dictionary for coordinator.

        Returns:
            dict: Current device state
        """
        return {
            "state": self.current_state,
            "water_weight_percent": self.water_weight_percent,
            "water_weight": self.water_weight,
            "is_water_detected": self.is_water_detected,
            "is_low_water": self.is_low_water,
            "needs_filter_replacement": self.needs_filter_replacement,
            "filter_next_replacement_timestamp": self.filter_next_replacement_timestamp,
            "is_light_enabled": self.is_light_enabled,
            "is_light_on": self.is_light_on,
            "battery_level": self.battery_level,
            "battery_state": self.battery_state,
            "error_code": self.error_code,
            "rssi": self._heartbeat.rssi,
            "is_online": self.is_online,
            "last_seen": self.last_seen,
            "seconds_since_heartbeat": self.seconds_since_last_heartbeat,
        }

    # ==================== MQTT Message Handlers ====================

    @callback
    def _handle_event_message(self, msg: MQTTMessage) -> None:
        """Handle incoming event messages for water fountain.

        Args:
            msg: MQTT message received
        """
        try:
            payload: dict = json.loads(msg.payload)
            cmd = payload.get("cmd")
            update: bool = True

            if cmd == "ATTR_PUSH_EVENT":
                self._attr_state.from_mqtt_payload(payload)
                _LOGGER.debug(
                    "Updated fountain attributes: light=%s, lowWater=%s, battery=%s%%",
                    self._attr_state.lightSwitch,
                    self._attr_state.lowWater,
                    self._attr_state.electricQuantity,
                )

            elif cmd == "WATER_CAP_EVENT":
                self._water_cap_state.from_mqtt_payload(payload)
                _LOGGER.debug(
                    "Updated water capacity: weight=%s%% (%sg), radarDetected=%s, batch=%s/%s",
                    self._water_cap_state.weightPercent,
                    self._water_cap_state.weight,
                    self._water_cap_state.radarDetected,
                    self._water_cap_state.batchIndex,
                    self._water_cap_state.totalBatches,
                )

            elif cmd == "DEVICE_START_EVENT":
                self._startup_info.from_mqtt_payload(payload)
                _LOGGER.info(
                    "Fountain started: %s", self._startup_info.softwareVersion
                )

            else:
                _LOGGER.warning("Unknown fountain event command: %s", cmd)
                update = False

            # Notify callback of state change
            if self._state_change_callback and update:
                _LOGGER.debug("Updating values from fountain state change")
                self.hass.async_create_task(self._state_change_callback())

        except Exception as err:
            _LOGGER.exception("Error handling fountain event message: %s", err)

    def _handle_device_specific_control_response(  # noqa: PLR6301
        self, cmd: str, payload: dict
    ) -> bool:
        """Handle water fountain-specific control responses.

        Args:
            cmd: Command name from the response
            payload: Full response payload

        Returns:
            bool: True if response was handled
        """
        # Currently no control commands implemented for fountain
        # Add handlers here when you implement pump control, light control, etc.
        _LOGGER.debug("Fountain control response: %s - %s", cmd, payload)
        return False

    # ==================== Lifecycle ====================

    async def _device_specific_start(self) -> None:  # noqa: PLR6301
        """Perform water fountain-specific initialization."""
        _LOGGER.debug("Water fountain initialization complete")
        # Device will send ATTR_PUSH_EVENT and WATER_CAP_EVENT automatically

    async def _device_specific_cleanup(self) -> None:
        """Perform water fountain-specific cleanup."""
        # No specific cleanup needed for water fountain

    # ==================== Water Fountain Commands ====================
    # Add control methods here when you determine the MQTT commands
    # For example:
    #
    # async def toggle_light(self) -> None:
    #     """Toggle the fountain light."""
    #     # Implement when you know the MQTT command structure
    #     pass
