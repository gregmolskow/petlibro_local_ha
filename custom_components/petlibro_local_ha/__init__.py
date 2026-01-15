"""Petlibro MQTT Home Assistant Integration.

This module initializes the Petlibro MQTT Home Assistant
integration that connects to Petlibro devices via MQTT.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import PetlibroCoordinator
from .ha_plaf301 import FEEDING_PLAN_SERVICE, PLAF301, FoodPlan
from .shared_const import (
    _LOGGER,
    TZ_OFFSET,
)
from .shared_const import (
    DOMAIN as DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


PLATFORMS: list[Platform] = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.COVER,
    Platform.BUTTON,
]


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

        # Start MQTT subscriptions and get device info
        await feeder.start()

        # Create coordinator
        coordinator: PetlibroCoordinator = PetlibroCoordinator(
            hass, entry, feeder
        )

        # Store coordinator in runtime data
        entry.runtime_data: PetlibroCoordinator = coordinator  # type: ignore

        entry.async_on_unload(entry.add_update_listener(async_options_updated))

        # Perform initial data fetch
        await coordinator.async_config_entry_first_refresh()

        # Forward setup to platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        _LOGGER.info("Successfully set up Petlibro device: %s", name)
        return True

    except Exception as err:
        _LOGGER.exception("Failed to set up Petlibro integration: %s", err)
        raise ConfigEntryNotReady from err


async def async_options_updated(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Handle options update.

    Args:
        hass: Home Assistant instance
        entry: Config entry
    """
    coordinator: PetlibroCoordinator = entry.runtime_data
    feeding_plan = FEEDING_PLAN_SERVICE()
    feeding_schedules = entry.options.get("feeding_schedules", [])
    for schedule in feeding_schedules:
        time = ":".join(schedule["time"].split(":")[:2])
        hours, minutes = map(int, time.split(":"))

        # Convert local time to UTC by subtracting timezone offset
        utc_hours = (hours - int(TZ_OFFSET)) % 24
        utc_time_str = f"{utc_hours:02d}:{minutes:02d}"
        food_plan = FoodPlan(
            grainNum=schedule["portions"],
            executionTime=utc_time_str,
            planId=schedule.get("planId"),
        )
        feeding_plan.add_plan(food_plan)

    _LOGGER.debug(
        "Updating feeding plan with schedules: %s", feeding_plan.to_dict()
    )

    if feeding_schedules:
        await coordinator.feeder.update_feeding_plan_service(feeding_plan)

        # Request refresh to get updated state
        await coordinator.async_request_refresh()


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
