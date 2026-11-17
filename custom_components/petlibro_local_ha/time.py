"""Support for Petlibro feeding schedule time entities."""

from __future__ import annotations

from datetime import time as dt_time
from typing import Any

from homeassistant.components.time import TimeEntity
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
    """Set up Petlibro dynamic schedule time entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device = hass.data[DOMAIN][entry.entry_id]["device"]

    tracked_plan_ids = set()

    @callback
    def async_add_dynamic_entities() -> None:
        """Check for feeding plans and dynamically add time entities."""
        nonlocal tracked_plan_ids
        plans = device.feeding_schedule.get("plans", [])
        new_entities = []

        for plan in plans:
            plan_id = plan.get("planId")
            if plan_id and plan_id not in tracked_plan_ids:
                tracked_plan_ids.add(plan_id)
                new_entities.append(
                    PetlibroScheduleTimeEntity(coordinator, device, plan_id)
                )

        if new_entities:
            async_add_entities(new_entities)

    async_add_dynamic_entities()
    coordinator.async_add_listener(async_add_dynamic_entities)


class PetlibroScheduleTimeEntity(CoordinatorEntity, TimeEntity):
    """Representation of a dynamic Petlibro feeding time slot."""

    def __init__(self, coordinator, device, plan_id: Any) -> None:
        """Initialize the time entity."""
        super().__init__(coordinator)
        self._device = device
        self._plan_id = plan_id

        self._attr_name = f"{device.name} Schedule {plan_id} Time"
        self._attr_unique_id = f"{device._sn}_schedule_{plan_id}_time"
        self._attr_icon = "mdi:clock-outline"

    def _get_plan(self) -> dict | None:
        """Helper to retrieve this specific plan dict."""
        plans = self._device.feeding_schedule.get("plans", [])
        for plan in plans:
            if plan.get("planId") == self._plan_id:
                return plan
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._get_plan() is not None

    @property
    def native_value(self) -> dt_time | None:
        """Return the current time for this schedule slot."""
        plan = self._get_plan()
        if plan and (time_str := plan.get("executionTime")):
            try:
                parts = time_str.split(":")
                return dt_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                pass
        return None

    async def async_set_value(self, value: dt_time) -> None:
        """Update the execution time and push to device."""
        time_str = value.strftime("%H:%M")
        plans = self._device.feeding_schedule.get("plans", [])

        for plan in plans:
            if plan.get("planId") == self._plan_id:
                plan["executionTime"] = time_str
                break

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
