"""Petlibro MQTT Home Assistant Integration.

This module initializes the Petlibro MQTT Home Assistant
integration that connects to Petlibro devices via MQTT.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .coordinator import PetlibroCoordinator
from .ha_plaf301 import FEEDING_PLAN_SERVICE, PLAF301, FoodPlan
from .ha_plwf116 import PLWF116
from .schedule_helpers import (
    MAX_FEEDING_PLANS as MAX_FEEDING_PLANS,
)
from .schedule_helpers import (
    ScheduleValidationError,
    check_duplicate_schedule,
    check_max_schedules,
    validate_portions,
    validate_repeat_days,
    validate_schedule_list,
    validate_time_string,
)
from .shared_const import (
    _LOGGER,
    DOMAIN,
    local_time_to_utc,
    utc_to_local_time,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall


# Platform mapping by device type (Updated to include number and time platforms for feeders)
FEEDER_PLATFORMS: list[Platform] = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.COVER,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.TIME,
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

        # Register domain-level services (only once, on the first entry)
        if not hass.services.has_service(DOMAIN, "set_feeding_schedule"):
            _register_services(hass)

        return True

    except Exception as err:
        _LOGGER.exception("Failed to set up Petlibro integration: %s", err)
        raise ConfigEntryNotReady from err


# ==================== Service helpers ====================


def _get_feeder_for_device_id(
    hass: HomeAssistant, device_id: str
) -> tuple[PLAF301, ConfigEntry]:
    """Resolve *device_id* to a feeder instance and its config entry.

    Raises:
        vol.Invalid: If the device cannot be found or is not a feeder.
    """
    dev_reg = dr.async_get(hass)
    device_entry = dev_reg.async_get(device_id)
    if device_entry is None:
        raise vol.Invalid(f"Device {device_id} not found")

    # Walk config entries looking for a matching one
    for entry_id in device_entry.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            continue
        runtime_data = getattr(entry, "runtime_data", None)
        if not runtime_data:
            continue
        if runtime_data.get("device_type") != "feeder":
            raise vol.Invalid(
                "This service is only available for feeder devices"
            )
        return runtime_data["device"], entry

    raise vol.Invalid(
        f"No Petlibro feeder config entry found for device {device_id}"
    )


def _device_schedules_as_local(
    feeder: PLAF301,
) -> list[dict[str, Any]]:
    """Return the feeder's current schedule list converted to local time."""
    result: list[dict[str, Any]] = []
    for plan in feeder.feeding_schedule.get("plans", []):
        utc_time = plan.get("executionTime", "")
        raw_days = plan.get("repeatDay") or [1, 2, 3, 4, 5, 6, 7]
        portions = plan.get("grainNum", 1)
        plan_id = plan.get("planId")

        if not utc_time:
            continue

        try:
            local_time, local_days = utc_to_local_time(utc_time, raw_days)
        except Exception:
            local_time = utc_time
            local_days = raw_days

        entry: dict[str, Any] = {
            "time": local_time,
            "portions": portions,
            "repeatDay": local_days,
        }
        if plan_id is not None:
            entry["planId"] = plan_id
        result.append(entry)

    result.sort(key=lambda s: s["time"])
    return result


async def _push_schedules_to_device(
    hass: HomeAssistant,
    feeder: PLAF301,
    config_entry: ConfigEntry,
    local_schedules: list[dict[str, Any]],
) -> None:
    """Convert *local_schedules* to UTC, push to the feeder, and update options."""
    feeding_plan = FEEDING_PLAN_SERVICE()

    for idx, schedule in enumerate(local_schedules):
        time_str = schedule["time"]
        portions = schedule.get("portions", 1)
        repeat_days = schedule.get("repeatDay") or [1, 2, 3, 4, 5, 6, 7]

        utc_time_str, shifted_days = local_time_to_utc(time_str, repeat_days)
        plan_id = schedule.get("planId")

        food_plan = FoodPlan(
            grainNum=portions,
            executionTime=utc_time_str,
            planId=plan_id,
            repeatDay=shifted_days,
        )
        feeding_plan.add_plan(food_plan)

        _LOGGER.debug(
            "Service: plan %d  local=%s  utc=%s  portions=%d  days=%s",
            idx,
            time_str,
            utc_time_str,
            portions,
            shifted_days,
        )

    await feeder.update_feeding_plan_service(feeding_plan)

    # Persist to config-entry options so the UI stays in sync
    new_options = dict(config_entry.options)
    new_options["feeding_schedules"] = local_schedules
    hass.config_entries.async_update_entry(config_entry, options=new_options)

    # Refresh coordinator
    runtime = config_entry.runtime_data
    coordinator: PetlibroCoordinator = runtime["coordinator"]
    await coordinator.async_request_refresh()


def _register_services(hass: HomeAssistant) -> None:
    """Register all petlibro_local_ha services."""

    # ── set_feeding_schedule ──────────────────────────────────────────

    async def handle_set_feeding_schedule(call: ServiceCall) -> None:
        """Replace the entire feeding schedule."""
        device_id: str = call.data["device_id"]
        raw_schedules: list[dict[str, Any]] = call.data["schedules"]

        feeder, config_entry = _get_feeder_for_device_id(hass, device_id)

        # Validate the full list (duplicates + max checked inside)
        try:
            validated = validate_schedule_list(raw_schedules)
        except ScheduleValidationError as exc:
            raise vol.Invalid(str(exc)) from exc

        _LOGGER.info(
            "Service set_feeding_schedule: pushing %d schedules to %s",
            len(validated),
            device_id,
        )
        await _push_schedules_to_device(hass, feeder, config_entry, validated)

    hass.services.async_register(
        DOMAIN,
        "set_feeding_schedule",
        handle_set_feeding_schedule,
    )

    # ── add_feeding_schedule ──────────────────────────────────────────

    async def handle_add_feeding_schedule(call: ServiceCall) -> None:
        """Add a single meal to the existing schedule."""
        device_id: str = call.data["device_id"]

        feeder, config_entry = _get_feeder_for_device_id(hass, device_id)

        # Build new entry
        try:
            time_str = validate_time_string(call.data["time"])
            portions = validate_portions(call.data.get("portions", 1))
            days = validate_repeat_days(call.data.get("repeat_days"))
        except ScheduleValidationError as exc:
            raise vol.Invalid(str(exc)) from exc

        # Get current schedules from device (converted to local)
        current = _device_schedules_as_local(feeder)

        # Validate limits
        max_err = check_max_schedules(current, adding=1)
        if max_err:
            raise vol.Invalid(max_err)

        dup_err = check_duplicate_schedule(time_str, days, current)
        if dup_err:
            raise vol.Invalid(dup_err)

        current.append({
            "time": time_str,
            "portions": portions,
            "repeatDay": days,
        })

        _LOGGER.info(
            "Service add_feeding_schedule: adding %s (%d portions) to %s",
            time_str,
            portions,
            device_id,
        )
        await _push_schedules_to_device(hass, feeder, config_entry, current)

    hass.services.async_register(
        DOMAIN,
        "add_feeding_schedule",
        handle_add_feeding_schedule,
    )

    # ── remove_feeding_schedule ───────────────────────────────────────

    async def handle_remove_feeding_schedule(call: ServiceCall) -> None:
        """Remove meal(s) matching a given time."""
        device_id: str = call.data["device_id"]
        try:
            remove_time = validate_time_string(call.data["time"])
        except ScheduleValidationError as exc:
            raise vol.Invalid(str(exc)) from exc

        feeder, config_entry = _get_feeder_for_device_id(hass, device_id)
        current = _device_schedules_as_local(feeder)

        updated = [s for s in current if s["time"] != remove_time]

        if len(updated) == len(current):
            _LOGGER.warning(
                "Service remove_feeding_schedule: no schedule at %s found",
                remove_time,
            )
            return

        removed_count = len(current) - len(updated)
        _LOGGER.info(
            "Service remove_feeding_schedule: removed %d schedule(s) at %s from %s",
            removed_count,
            remove_time,
            device_id,
        )
        await _push_schedules_to_device(hass, feeder, config_entry, updated)

    hass.services.async_register(
        DOMAIN,
        "remove_feeding_schedule",
        handle_remove_feeding_schedule,
    )

    # ── sync_feeding_schedule ─────────────────────────────────────────

    async def handle_sync_feeding_schedule(call: ServiceCall) -> None:
        """Force a re-read of the schedule from the physical feeder."""
        device_id: str = call.data["device_id"]

        feeder, config_entry = _get_feeder_for_device_id(hass, device_id)

        _LOGGER.info(
            "Service sync_feeding_schedule: requesting schedule from %s",
            device_id,
        )
        await feeder.request_feeding_schedule()

        # Update options with what the device reports
        local_schedules = _device_schedules_as_local(feeder)
        new_options = dict(config_entry.options)
        new_options["feeding_schedules"] = local_schedules
        hass.config_entries.async_update_entry(
            config_entry, options=new_options
        )

        # Refresh coordinator
        runtime = config_entry.runtime_data
        coordinator: PetlibroCoordinator = runtime["coordinator"]
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "sync_feeding_schedule",
        handle_sync_feeding_schedule,
    )

    _LOGGER.debug("Registered petlibro_local_ha services")


def _unregister_services(hass: HomeAssistant) -> None:
    """Remove all petlibro_local_ha services."""
    for svc in (
        "set_feeding_schedule",
        "add_feeding_schedule",
        "remove_feeding_schedule",
        "sync_feeding_schedule",
    ):
        hass.services.async_remove(DOMAIN, svc)
    _LOGGER.debug("Unregistered petlibro_local_ha services")


def _normalize_schedule_for_comparison(
    sched: dict | Any,
) -> tuple[str, int, tuple[int, ...]]:
    """Normalize schedule to (utc_execution_time, portions, repeat_day_tuple)."""
    if isinstance(sched, dict):
        portions = sched.get("portions", sched.get("grainNum", 1))
        raw_days = sched.get("repeatDay") or [1, 2, 3, 4, 5, 6, 7]
        if sched.get("executionTime"):
            utc_time = sched["executionTime"]
            repeat_days = raw_days
        elif sched.get("time"):
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

    current_normalized = sorted([
        _normalize_schedule_for_comparison(s) for s in current
    ])
    new_normalized = sorted([
        _normalize_schedule_for_comparison(s) for s in new
    ])

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

        # Unregister services if this is the last config entry
        remaining = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id
        ]
        if not remaining and hass.services.has_service(
            DOMAIN, "set_feeding_schedule"
        ):
            _unregister_services(hass)

        _LOGGER.info("Successfully unloaded Petlibro integration")

    return unload_ok
