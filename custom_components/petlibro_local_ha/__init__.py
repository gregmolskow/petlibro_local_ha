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
from .ha_plwf116 import PLWF116
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


# Platform mapping by device type
FEEDER_PLATFORMS: list[Platform] = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.COVER,
    Platform.BUTTON,
]

FOUNTAIN_PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
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
    device_type: str = config.get("petlibro_device_type", "feeder")
    sn: str = config.get("petlibro_serial_number", "")
    name: str = config.get("petlibro_device_name", f"Petlibro {device_type.title()}")

    if not sn:
        _LOGGER.error("No serial number provided in config entry")
        return False

    try:
        # Create device instance based on type
        if device_type == "feeder":
            device = PLAF301(hass, sn, name)
            platforms = FEEDER_PLATFORMS
        elif device_type == "fountain":
            device = PLWF116(hass, sn, name)
            platforms = FOUNTAIN_PLATFORMS
        else:
            _LOGGER.error("Unknown device type: %s", device_type)
            return False

        # Start MQTT subscriptions and get device info
        await device.start()

        # Create coordinator for this device
        coordinator: PetlibroCoordinator = PetlibroCoordinator(hass, entry, device)

        # Store coordinator and device in runtime data
        entry.runtime_data = {
            "coordinator": coordinator,
            "device": device,
            "device_type": device_type,
        }

        entry.async_on_unload(entry.add_update_listener(async_options_updated))

        # Perform initial data fetch
        await coordinator.async_config_entry_first_refresh()

        # Forward setup to appropriate platforms
        await hass.config_entries.async_forward_entry_setups(entry, platforms)

        _LOGGER.info("Successfully set up Petlibro device: %s (%s)", name, sn)
        return True

    except Exception as err:
        _LOGGER.exception("Failed to set up Petlibro integration: %s", err)
        raise ConfigEntryNotReady from err


def _schedules_are_equal(current: list, new: list) -> bool:
    """Check if two schedule lists are equivalent."""
    if len(current) != len(new):
        return False

    # Convert to comparable format (UTC time + portions)
    def normalize_schedule(sched):
        if isinstance(sched, dict):
            time_str = sched.get("time", "")
            portions = sched.get("portions", 1)
            execution_time = sched.get("executionTime", "")
        else:
            execution_time = getattr(sched, "executionTime", "")
            portions = getattr(sched, "grainNum", 1)
            time_str = ""

        return (execution_time or time_str, portions)

    current_normalized = sorted([normalize_schedule(s) for s in current])
    new_normalized = sorted([normalize_schedule(s) for s in new])

    return current_normalized == new_normalized


async def async_options_updated(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Handle options update.

    Args:
        hass: Home Assistant instance
        entry: Config entry
    """
    runtime_data = entry.runtime_data
    coordinator: PetlibroCoordinator = runtime_data["coordinator"]
    device_type: str = runtime_data["device_type"]

    # Only process feeding schedules for feeders
    if device_type != "feeder":
        _LOGGER.debug("Skipping schedule update for non-feeder device")
        return

    # Get current schedules from device
    current_schedules = coordinator.feeder.feeding_schedule.get("plans", [])
    new_schedules = entry.options.get("feeding_schedules", [])

    # Compare schedules - only update if different
    if _schedules_are_equal(current_schedules, new_schedules):
        _LOGGER.debug("Feeding schedules unchanged, skipping update")
        return

    feeding_plan = FEEDING_PLAN_SERVICE()
    feeding_schedules = entry.options.get("feeding_schedules", [])

    _LOGGER.debug("Processing %d feeding schedules", len(feeding_schedules))

    for idx, schedule in enumerate(feeding_schedules):
        # Validate schedule has required fields
        if "time" not in schedule or "portions" not in schedule:
            _LOGGER.warning("Skipping invalid schedule %d: %s", idx, schedule)
            continue

        time_str = schedule["time"]
        portions = schedule.get("portions", 1)

        # Validate portions
        if portions is None or portions == 0:
            _LOGGER.warning(
                "Schedule %d has invalid portions (%s), defaulting to 1",
                idx,
                portions,
            )
            portions = 1

        # Validate time format
        if not isinstance(time_str, str) or ":" not in time_str:
            _LOGGER.warning("Schedule %d has invalid time format: %s", idx, time_str)
            continue

        try:
            # Extract hours and minutes (handle HH:MM:SS or HH:MM format)
            time_parts = time_str.split(":")
            hours = int(time_parts[0])
            minutes = int(time_parts[1])

            # Validate time values
            if not (0 <= hours < 24 and 0 <= minutes < 60):  # noqa: PLR2004
                _LOGGER.warning(
                    "Schedule %d has invalid time values: %02d:%02d",
                    idx,
                    hours,
                    minutes,
                )
                continue

            # Convert local time to UTC by subtracting timezone offset
            utc_hours = (hours - int(TZ_OFFSET)) % 24
            utc_time_str = f"{utc_hours:02d}:{minutes:02d}"

            # Get planId if it exists (for updates), otherwise None (new plan)
            plan_id = schedule.get("planId")

            food_plan = FoodPlan(
                grainNum=portions,
                executionTime=utc_time_str,
                planId=plan_id,
            )
            feeding_plan.add_plan(food_plan)

            _LOGGER.debug(
                "Added plan %d: local=%s, utc=%s, portions=%d, planId=%s",
                idx,
                time_str,
                utc_time_str,
                portions,
                plan_id,
            )

        except (ValueError, IndexError) as e:
            _LOGGER.warning("Error processing schedule %d (%s): %s", idx, schedule, e)
            continue

    _LOGGER.debug(
        "Updating feeding plan with %d schedules: %s",
        len(feeding_plan.plans),
        feeding_plan.to_dict(),
    )

    if feeding_schedules:
        await coordinator.feeder.update_feeding_plan_service(feeding_plan)

        # Request refresh to get updated state
        await coordinator.async_request_refresh()
    else:
        _LOGGER.info("No feeding schedules to update")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload was successful
    """
    runtime_data = entry.runtime_data
    device_type: str = runtime_data["device_type"]

    # Determine platforms to unload
    if device_type == "feeder":
        platforms = FEEDER_PLATFORMS
    elif device_type == "fountain":
        platforms = FOUNTAIN_PLATFORMS
    else:
        platforms = []

    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    if unload_ok:
        device = runtime_data["device"]

        # Clean up device
        await device.cleanup()

        _LOGGER.info("Successfully unloaded Petlibro integration")

    return unload_ok
