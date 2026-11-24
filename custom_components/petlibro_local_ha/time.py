"""Support for Petlibro feeding schedule time entities."""

from __future__ import annotations

from datetime import time as dt_time
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import PetlibroCoordinator
from .schedule_helpers import get_plan_display_index
from .shared_const import DOMAIN, local_time_to_utc, utc_to_local_time


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Petlibro schedule time entities dynamically."""
    runtime_data = entry.runtime_data
    coordinator: PetlibroCoordinator = runtime_data["coordinator"]
    device = runtime_data["device"]

    if hasattr(device, "feeding_schedule"):
        tracked_plan_ids: set[Any] = set()

        @callback
        def async_add_dynamic_times() -> None:
            """Check for feeding plans and dynamically add time entities."""
            nonlocal tracked_plan_ids
            plans = device.feeding_schedule.get("plans", [])
            new_entities: list[TimeEntity] = []

            for idx, plan in enumerate(plans, start=1):
                plan_id = plan.get("planId")
                if plan_id and plan_id not in tracked_plan_ids:
                    tracked_plan_ids.add(plan_id)
                    new_entities.append(
                        PetlibroScheduleTimeEntity(
                            coordinator, device, plan_id, idx
                        )
                    )

            if new_entities:
                async_add_entities(new_entities)

        # Initial population on startup
        async_add_dynamic_times()

        # Listen for updates to catch schedule additions/deletions
        coordinator.async_add_listener(async_add_dynamic_times)


class PetlibroScheduleTimeEntity(CoordinatorEntity, TimeEntity):
    """Representation of a Petlibro feeding time slot."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator,
        device,
        plan_id: Any,
        display_id: int | None = None,
    ) -> None:
        """Initialize the time entity."""
        super().__init__(coordinator)
        self._device = device
        self._plan_id = plan_id
        self._display_id = display_id if display_id is not None else plan_id

        self._attr_unique_id = f"{device.serial_number}_schedule_{plan_id}_time"

    @property
    def name(self) -> str:
        """Return the display name using the 1-based schedule index."""
        idx = get_plan_display_index(
            self._device, self._plan_id, self._display_id
        )
        return f"Schedule {idx} Time"

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
        if not plans:
            plans = self.coordinator.config_entry.options.get(
                "feeding_schedules", []
            )

        for idx, plan in enumerate(plans):
            p_id = plan.get("planId") or (idx + 1)
            if p_id == self._plan_id:
                return plan
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available (only if the plan slot is currently populated)."""
        return super().available and self._get_plan() is not None

    @property
    def native_value(self) -> dt_time | None:
        """Return the current local time for this schedule slot."""
        plan = self._get_plan()
        if not plan:
            return None

        if utc_time := plan.get("executionTime"):
            try:
                local_time, _ = utc_to_local_time(
                    utc_time, plan.get("repeatDay")
                )
                parts = local_time.split(":")
                return dt_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                return None

        if local_time := plan.get("time"):
            try:
                parts = local_time.split(":")
                return dt_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                return None

        return None

    async def async_set_value(self, value: dt_time) -> None:
        """Update the execution time (local UI -> UTC device) and push to device."""
        local_time_str = value.strftime("%H:%M")
        plans = self._device.feeding_schedule.get("plans", [])

        found = False
        for idx, plan in enumerate(plans):
            p_id = plan.get("planId") or (idx + 1)
            if p_id == self._plan_id:
                raw_days = plan.get("repeatDay")
                if raw_days is None:
                    raw_days = [1, 2, 3, 4, 5, 6, 7]

                old_utc_time = plan.get("executionTime")
                if old_utc_time and raw_days:
                    _, local_days = utc_to_local_time(old_utc_time, raw_days)
                else:
                    local_days = raw_days

                utc_time_str, shifted_days = local_time_to_utc(
                    local_time_str, local_days
                )
                plan["executionTime"] = utc_time_str
                plan["repeatDay"] = shifted_days
                plan["planId"] = p_id
                found = True
                break

        if not found:
            return

        self._device._schedule.plans = []
        for plan_data in plans:
            self._device.add_feeding_plan(
                id=plan_data.get("planId"),
                time=plan_data.get("executionTime", plan_data.get("time")),
                amount=plan_data.get("grainNum", plan_data.get("portions", 1)),
                repeat_day=plan_data.get("repeatDay", [1, 2, 3, 4, 5, 6, 7]),
            )

        await self._device.update_feeding_plan_service(self._device._schedule)
        await self.coordinator.async_request_refresh()
