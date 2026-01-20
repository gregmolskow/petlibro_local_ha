"""PLWF116 Petlibro water fountain device handler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .ha_petlibro_base import PetlibroDeviceBase
from .plwf116_const import (
    ERROR_FILTER_REPLACE,
    ERROR_LOW_WATER,
    ERROR_NONE,
    ERROR_UNKNOWN,
    WaterFountainState,
)
from .shared_const import (
    _LOGGER,
    MODEL_PLWF116,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


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

        # Water fountain-specific state tracking
        self._pump_running = False
        self._filter_life = 100  # Percentage
        self._water_level = 100  # Percentage

    # ==================== Water Fountain-Specific Properties ====================

    @property
    def is_pump_running(self) -> bool:
        """Check if the pump is currently running."""
        return self._pump_running

    @property
    def water_level(self) -> int:
        """Get water level percentage (0-100)."""
        return self._water_level

    @property
    def filter_life(self) -> int:
        """Get filter life percentage (0-100)."""
        return self._filter_life

    @property
    def is_low_water(self) -> bool:
        """Check if water level is low."""
        return self._water_level < 20

    @property
    def needs_filter_change(self) -> bool:
        """Check if filter needs replacement."""
        return self._filter_life < 10

    @property
    def current_state(self) -> WaterFountainState:
        """Get the current state of the device."""
        if self.is_low_water:
            return WaterFountainState.ERROR
        if self.needs_filter_change:
            return WaterFountainState.WARNING
        if self.is_pump_running:
            return WaterFountainState.RUNNING
        return WaterFountainState.IDLE

    @property
    def error_code(self) -> str:
        """Get current error code."""
        if self.is_low_water:
            return ERROR_LOW_WATER
        if self.needs_filter_change:
            return ERROR_FILTER_REPLACE
        if self.current_state == WaterFountainState.ERROR:
            return ERROR_UNKNOWN
        return ERROR_NONE

    # ==================== State Management ====================

    def get_state_dict(self) -> dict[str, Any]:
        """Get state as dictionary for coordinator.

        Returns:
            dict: Current device state
        """
        return {
            "state": self.current_state,
            "is_pump_running": self.is_pump_running,
            "water_level": self.water_level,
            "filter_life": self.filter_life,
            "is_low_water": self.is_low_water,
            "needs_filter_change": self.needs_filter_change,
            "error_code": self.error_code,
            "rssi": self._heartbeat.rssi,
            "is_online": self.is_online,
            "last_seen": self.last_seen,
            "seconds_since_heartbeat": self.seconds_since_last_heartbeat,
        }

    # ==================== Event Handlers ====================

    def _handle_device_specific_event(self, cmd: str, payload: dict) -> bool:
        """Handle water fountain-specific event messages.

        Args:
            cmd: Command name from the event
            payload: Full event payload

        Returns:
            bool: True if event was handled and should trigger update
        """
        if cmd == "PUMP_STATE_EVENT":
            self._pump_running = payload.get("pumpRunning", False)
            _LOGGER.debug("Pump running: %s", self._pump_running)
            return True

        if cmd == "WATER_LEVEL_EVENT":
            self._water_level = payload.get("waterLevel", 100)
            _LOGGER.debug("Water level: %s%%", self._water_level)
            return True

        if cmd == "FILTER_STATUS_EVENT":
            self._filter_life = payload.get("filterLife", 100)
            _LOGGER.debug("Filter life: %s%%", self._filter_life)
            return True

        return False

    def _handle_device_specific_control_response(
        self, cmd: str, payload: dict
    ) -> bool:
        """Handle water fountain-specific control responses.

        Args:
            cmd: Command name from the response
            payload: Full response payload

        Returns:
            bool: True if response was handled
        """
        if cmd == "PUMP_CONTROL_RESPONSE":
            _LOGGER.info("Pump control command acknowledged")
            return True

        if cmd == "FILTER_RESET_RESPONSE":
            self._filter_life = 100
            _LOGGER.info("Filter life reset to 100%%")
            return True

        return False

    # ==================== Lifecycle ====================

    async def _device_specific_start(self) -> None:
        """Perform water fountain-specific initialization."""
        # Request current water level and filter status
        _LOGGER.debug("Water fountain initialization complete")
        # TODO: Add specific initialization commands if needed

    async def _device_specific_cleanup(self) -> None:
        """Perform water fountain-specific cleanup."""
        # No specific cleanup needed for water fountain

    # ==================== Water Fountain Commands ====================

    async def start_pump(self) -> None:
        """Start the water pump."""
        _LOGGER.info("Starting water pump")
        # TODO: Implement actual MQTT command based on device protocol
        # await self._publish_command(PUMP_CONTROL_SERVICE(running=True))
        self._pump_running = True
        await self._notify_state_change()

    async def stop_pump(self) -> None:
        """Stop the water pump."""
        _LOGGER.info("Stopping water pump")
        # TODO: Implement actual MQTT command based on device protocol
        # await self._publish_command(PUMP_CONTROL_SERVICE(running=False))
        self._pump_running = False
        await self._notify_state_change()

    async def toggle_pump(self) -> None:
        """Toggle the pump state."""
        if self.is_pump_running:
            await self.stop_pump()
        else:
            await self.start_pump()

    async def reset_filter_life(self) -> None:
        """Reset filter life indicator (after replacing filter)."""
        _LOGGER.info("Resetting filter life indicator")
        # TODO: Implement actual MQTT command based on device protocol
        # await self._publish_command(FILTER_RESET_SERVICE())
        self._filter_life = 100
        await self._notify_state_change()
