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
    DOMAIN,
    local_time_to_utc,
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


def detect_device_type(serial_number: str) -> str:
    """Detect device type from serial number prefix.

    Args:
        serial_number: Device serial number

    Returns:
        Device type: "feeder" or "fountain"
    """
    sn_upper = serial_number.upper()

    if sn_upper.startswith("AF"):
        return "feeder"
    if sn_upper.startswith("WF"):
        return "fountain"
    # Default to feeder for backward compatibility
    _LOGGER.warning(
        "Unknown serial number prefix for %s, defaulting to feeder",
        serial_number,
    )
    return "feeder"


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

    if not sn:
        _LOGGER.error("No serial number provided in config entry")
        return False

    # Auto-detect device type from serial number if not specified
    device_type: str = config.get("petlibro_device_type")
    if not device_type:
        device_type = detect_device_type(sn)
        _LOGGER.info(
            "Auto-detected device type '%s' from serial number %s",
            device_type,
            sn,
        )

    name: str = config.get(
        "petlibro_device_name", f"Petlibro {device_type.title()}"
    )

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
        coordinator: PetlibroCoordinator = PetlibroCoordinator(
            hass, entry, device
        )

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


def _normalize_schedule_for_comparison(
    sched: dict | Any,
) -> tuple[str, int, tuple[int, ...]]:
    """Normalize schedule to (utc_execution_time, portions, repeat_day_tuple)."""
    if isinstance(sched, dict):
        portions = sched.get("portions", sched.get("grainNum", 1))
        raw_days = sched.get("repeatDay") or [1, 2, 3, 4, 5, 6, 7]
        if "executionTime" in sched and sched["executionTime"]:
            utc_time = sched["executionTime"]
            repeat_days = raw_days
        elif "time" in sched and sched["time"]:
            try:
                utc_time, repeat_days = local_time_to_utc(
                    sched["time"], raw_days
                )
            except Exception:
                utc_time = sched["time"]
                repeat_days = raw_days
        else:
            utc_time = ""
            repeat_days = raw_days
    else:
        portions = getattr(sched, "grainNum", 1)
        raw_days = getattr(sched, "repeatDay", None) or [1, 2, 3, 4, 5, 6, 7]
        utc_time = getattr(sched, "executionTime", "")
        repeat_days = raw_days

    return (utc_time, portions or 1, tuple(sorted(repeat_days)))


def _schedules_are_equal(current: list, new: list) -> bool:
    """Check if two schedule lists are equivalent."""
    if len(current) != len(new):
        return False

    current_normalized = sorted(
        [_normalize_schedule_for_comparison(s) for s in current]
    )
    new_normalized = sorted(
        [_normalize_schedule_for_comparison(s) for s in new]
    )

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
    _LOGGER.debug("Processing %d feeding schedules", len(new_schedules))

    for idx, schedule in enumerate(new_schedules):
        # Validate schedule has required fields
        if "time" not in schedule or "portions" not in schedule:
            _LOGGER.warning("Skipping invalid schedule %d: %s", idx, schedule)
            continue

        time_str = schedule["time"]
        portions = schedule.get("portions", 1)
        repeat_days = schedule.get("repeatDay") or [1, 2, 3, 4, 5, 6, 7]

        # Validate portions
        if portions is None or portions == 0:
            _LOGGER.warning(
                "Schedule %d has invalid portions (%s), defaulting to 1",
                idx,
                portions,
            )
            portions = 1

        try:
            # Convert local time to UTC and shift days if crossing midnight
            utc_time_str, shifted_days = local_time_to_utc(
                time_str, repeat_days
            )

            # Get planId if it exists (for updates), otherwise None (new plan)
            plan_id = schedule.get("planId")

            food_plan = FoodPlan(
                grainNum=portions,
                executionTime=utc_time_str,
                planId=plan_id,
                repeatDay=shifted_days,
            )
            feeding_plan.add_plan(food_plan)

            _LOGGER.debug(
                "Added plan %d: local=%s, utc=%s, portions=%d, days=%s, planId=%s",
                idx,
                time_str,
                utc_time_str,
                portions,
                shifted_days,
                plan_id,
            )

        except (ValueError, IndexError) as e:
            _LOGGER.warning(
                "Error processing schedule %d (%s): %s", idx, schedule, e
            )
            continue

    _LOGGER.debug(
        "Updating feeding plan with %d schedules: %s",
        len(feeding_plan.plans),
        feeding_plan.to_dict(),
    )

    await coordinator.feeder.update_feeding_plan_service(feeding_plan)
    await coordinator.async_request_refresh()


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

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, platforms
    )

    if unload_ok:
        device = runtime_data["device"]

        # Clean up device
        await device.cleanup()

        _LOGGER.info("Successfully unloaded Petlibro integration")

    return unload_ok
