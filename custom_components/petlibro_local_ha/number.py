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
        plans = device.feeding_schedule.get("plans", [])
        new_entities = []

        for plan in plans:
            plan_id = plan.get("planId")
            if plan_id and plan_id not in tracked_plan_ids:
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

    def __init__(self, coordinator, device, plan_id: Any) -> None:
        """Initialize the portion entity."""
        super().__init__(coordinator)
        self._device = device
        self._plan_id = plan_id

        self._attr_name = f"{device.name} Schedule {plan_id} Portions"
        self._attr_unique_id = f"{device._sn}_schedule_{plan_id}_portions"
        self._attr_native_min_value = 1
        self._attr_native_max_value = 10
        self._attr_native_step = 1
        self._attr_mode = NumberMode.BOX
        self._attr_icon = "mdi:food"

    def _get_plan(self) -> dict | None:
        """Helper to retrieve this specific plan dict from device schedule."""
        plans = self._device.feeding_schedule.get("plans", [])
        for plan in plans:
            if plan.get("planId") == self._plan_id:
                return plan
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available (plan exists)."""
        return super().available and self._get_plan() is not None

    @property
    def native_value(self) -> float | None:
        """Return the current portion count."""
        plan = self._get_plan()
        if plan:
            return plan.get("grainNum", 1)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Update portions for this specific plan and push changes via MQTT."""
        int_value = int(value)
        plans = self._device.feeding_schedule.get("plans", [])

        for plan in plans:
            if plan.get("planId") == self._plan_id:
                plan["grainNum"] = int_value
                break

        # Rebuild and push to physical feeder
        self._device._schedule.plans = []
        for plan_data in plans:
            self._device.add_feeding_plan(
                id=plan_data.get("planId"),
                time=plan_data.get("executionTime"),
                amount=plan_data.get("grainNum"),
                repeat_day=plan_data.get("repeatDay", [1, 2, 3, 4, 5, 6, 7]),
            )

        await self._device.update_feeding_plan_service(self._device._schedule)
        await self.coordinator.async_request_refresh()
