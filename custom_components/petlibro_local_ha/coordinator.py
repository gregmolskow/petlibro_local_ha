"""Data coordinator for Petlibro integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import _LOGGER, DEFAULT_SCAN_INTERVAL, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .ha_plaf301 import PLAF301


class PetlibroCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator to manage Petlibro feeder data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        feeder: PLAF301,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            config_entry: Config entry for this integration
            feeder: PLAF301 feeder instance
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

        self.feeder: PLAF301 = feeder

        # Register callback for immediate updates
        self.feeder.set_state_change_callback(self._on_state_change)

        self._state_change: bool = False

    async def _on_state_change(self) -> None:
        """Handle state change from feeder.

        This is called when MQTT messages arrive with state updates.
        """
        _LOGGER.debug("State change detected, refreshing coordinator")
        self._state_change = True
        # Update coordinator data immediately without waiting for interval
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict:
        """Fetch data from the feeder.

        Returns:
            dict: Current state data from the feeder

        Raises:
            UpdateFailed: If unable to fetch data
        """
        try:
            _LOGGER.info("State Chanege %s", self._state_change)
            if not self._state_change:
                # Request state update from device
                _LOGGER.debug("Petlibro coordinator requesting state update")
                await self.feeder.request_state_update()
            else:
                self._state_change = False

            # Return current status
            return self.feeder.get_state_dict()

        except Exception as err:
            _LOGGER.exception("Error updating Petlibro feeder data")
            msg = f"Error communicating with device: {err}"
            raise UpdateFailed(msg) from err
