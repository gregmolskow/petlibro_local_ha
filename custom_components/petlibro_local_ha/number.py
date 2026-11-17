"""Support for Petlibro feeding schedule portion entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .shared_const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Petlibro dynamic schedule portion entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device = hass.data[DOMAIN][entry.entry_id]["device"]

    tracked_plan_ids = set()

    @callback
    def async_add_dynamic_entities() -> None:
        """Check for feeding plans and dynamically add entities."""
        nonlocal tracked_plan_ids

        # Check active device plans first, falling back to config options
        plans = device.feeding_schedule.get("plans", [])
        if not plans:
            plans = entry.options.get("feeding_schedules", [])

        new_entities = []

        for idx, plan in enumerate(plans):
            # Fallback index if planId is missing
            plan_id = plan.get("planId") or (idx + 1)

            if plan_id not in tracked_plan_ids:
                tracked_plan_ids.add(plan_id)
                new_entities.append(
                    PetlibroSchedulePortionsEntity(coordinator, device, plan_id)
                )

        if new_entities:
            async_add_entities(new_entities)

    # Initial check on startup
    async_add_dynamic_entities()

    # Listen for coordinator updates to catch future additions/deletions
    coordinator.async_add_listener(async_add_dynamic_entities)


class PetlibroSchedulePortionsEntity(CoordinatorEntity, NumberEntity):
    """Representation of a dynamic Petlibro feeding portion slot."""

    _attr_has_entity_name = True
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:food"

    def __init__(self, coordinator, device, plan_id: Any) -> None:
        """Initialize the portion entity."""
        super().__init__(coordinator)
        self._device = device
        self._plan_id = plan_id

        self._attr_name = f"Schedule {plan_id} Portions"
        self._attr_unique_id = (
            f"{device.serial_number}_schedule_{plan_id}_portions"
        )

    @property
    def device_info(self) -> dict[str, Any]:
        """Link entity to the main Petlibro device entry."""
        return {
            "identifiers": {(DOMAIN, self._device.serial_number)},
            "name": self._device.name,
            "manufacturer": getattr(self._device, "manufacturer", "Petlibro"),
            "model": getattr(self._device, "model", "PLAF301"),
        }

    def _get_plan(self) -> dict | None:
        """Helper to retrieve this specific plan dict by ID or index match."""
        plans = self._device.feeding_schedule.get("plans", [])
        for idx, plan in enumerate(plans):
            p_id = plan.get("planId") or (idx + 1)
            if p_id == self._plan_id:
                return plan
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._get_plan() is not None

    @property
    def native_value(self) -> float | None:
        """Return the current portion count."""
        plan = self._get_plan()
        if plan:
            return float(plan.get("grainNum", plan.get("portions", 1)))
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Update portions for this specific plan and push changes via MQTT."""
        int_value = int(value)
        plans = self._device.feeding_schedule.get("plans", [])

        found = False
        for idx, plan in enumerate(plans):
            p_id = plan.get("planId") or (idx + 1)
            if p_id == self._plan_id:
                plan["grainNum"] = int_value
                plan["planId"] = p_id  # Ensure planId is stamped
                found = True
                break

        if not found:
            return

        # Rebuild and push to physical feeder
        self._device._schedule.plans = []
        for plan_data in plans:
            self._device.add_feeding_plan(
                id=plan_data.get("planId"),
                time=plan_data.get("executionTime", plan_data.get("time")),
                amount=plan_data.get("grainNum", plan_data.get("portions")),
                repeat_day=plan_data.get("repeatDay", [1, 2, 3, 4, 5, 6, 7]),
            )

        await self._device.update_feeding_plan_service(self._device._schedule)
        await self.coordinator.async_request_refresh()
