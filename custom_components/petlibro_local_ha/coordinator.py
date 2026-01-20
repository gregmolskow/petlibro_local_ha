"""Data coordinator for Petlibro integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .shared_const import _LOGGER, DEFAULT_SCAN_INTERVAL, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .ha_plaf301 import PLAF301
    from .ha_plwf116 import PLWF116


class PetlibroCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator to manage Petlibro device data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device: PLAF301 | PLWF116,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            config_entry: Config entry for this integration
            device: Device instance (PLAF301 or PLWF116)
        """
        # Get scan interval from options, fallback to default
        scan_interval = config_entry.options.get(
            "scan_interval",
            DEFAULT_SCAN_INTERVAL,
        )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval),
        )

        self.feeder = device  # Keep this name for backward compatibility
        self.device = device  # More generic name

        # Register callback for immediate updates
        self.device.set_state_change_callback(self._on_state_change)

        self._state_change: bool = False

    async def _on_state_change(self) -> None:
        """Handle state change from device.

        This is called when MQTT messages arrive with state updates.
        """
        _LOGGER.debug("State change detected, refreshing coordinator")
        self._state_change = True
        # Update coordinator data immediately without waiting for interval
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict:
        """Fetch data from the device.

        Returns:
            dict: Current state data from the device

        Raises:
            UpdateFailed: If unable to fetch data
        """
        try:
            _LOGGER.debug("State Change: %s", self._state_change)

            # Check if device is online
            if not self.device.is_online:
                _LOGGER.warning(
                    "Device appears offline - last heartbeat was %s seconds ago",
                    self.device.seconds_since_last_heartbeat,
                )

            if not self._state_change:
                # Request state update from device
                _LOGGER.debug("Petlibro coordinator requesting state update")
                await self.device.request_state_update()
            else:
                self._state_change = False

            # Return current status
            return self.device.get_state_dict()

        except Exception as err:
            _LOGGER.exception("Error updating Petlibro device data")
            msg = f"Error communicating with device: {err}"
            raise UpdateFailed(msg) from err
