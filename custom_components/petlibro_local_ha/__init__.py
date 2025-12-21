"""Petlibro MQTT Home Assistant Integration.

This module initializes the Petlibro MQTT Home Assistant
integration that connects to Petlibro devices via MQTT.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN as DOMAIN
from .coordinator import PetlibroCoordinator
from .ha_plaf301 import PLAF301

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.VACUUM]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Petlibro integration from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry containing user configuration

    Returns:
        True if setup was successful

    Raises:
        ConfigEntryNotReady: If MQTT connection fails
    """
    config = entry.data
    sn: str = config.get("petlibro_serial_number", "")
    name: str = config.get("petlibro_device_name", "Petlibro Feeder")

    if not sn:
        _LOGGER.error("No serial number provided in config entry")
        return False

    try:
        # Create feeder instance
        feeder = PLAF301(hass, sn, name)

        # Create coordinator
        coordinator = PetlibroCoordinator(hass, entry, feeder)

        # Store coordinator in runtime data
        entry.runtime_data = coordinator

        # Start MQTT subscriptions
        await feeder.start()

        # Perform initial data fetch
        await coordinator.async_config_entry_first_refresh()

        # Forward setup to platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        _LOGGER.info("Successfully set up Petlibro device: %s", name)
        return True

    except Exception as err:
        _LOGGER.exception("Failed to set up Petlibro integration: %s", err)
        raise ConfigEntryNotReady from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload was successful
    """
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )

    if unload_ok:
        coordinator: PetlibroCoordinator = entry.runtime_data
        await coordinator.feeder.cleanup()
        _LOGGER.info("Successfully unloaded Petlibro integration")

    return unload_ok
