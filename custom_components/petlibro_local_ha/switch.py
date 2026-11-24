"""Switch platform for Petlibro integration (supports device switches and dynamic schedules)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import PetlibroCoordinator
from .schedule_helpers import get_plan_display_index
from .shared_const import _LOGGER, DOMAIN, MAXIMUM_NUMBER_OF_PLANS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Petlibro switches (pump and dynamic schedule toggles)."""
    runtime_data = entry.runtime_data
    coordinator: PetlibroCoordinator = runtime_data["coordinator"]
    device = runtime_data["device"]

    # 1. Add pump switch for water fountain devices (PLWF116)
    if device.serial_number.upper().startswith("WF"):
        entities: list[SwitchEntity] = [
            PetlibroPumpSwitch(coordinator, entry, device)
        ]
        async_add_entities(entities, update_before_add=True)

    # 2. Dynamically track and add schedule enable/disable switches (if feeder supports schedules)
    if hasattr(device, "feeding_schedule"):
        tracked_plan_ids = set()

        @callback
        def async_add_dynamic_switches() -> None:
            """Check for feeding plans and dynamically add switch entities."""
            nonlocal tracked_plan_ids
            plans = device.feeding_schedule.get("plans", [])
            new_switches = []

            for idx, plan in enumerate(plans, start=1):
                plan_id = plan.get("planId")
                if plan_id and plan_id not in tracked_plan_ids:
                    tracked_plan_ids.add(plan_id)
                    new_switches.append(
                        PetlibroScheduleEnableSwitch(
                            coordinator, device, plan_id, idx
                        )
                    )

            # Add all of the place holder switches
            for idx in range(MAXIMUM_NUMBER_OF_PLANS - len(plans)):
                display_id = len(plans) + idx + 1
                plan_id = display_id
                if plan_id not in tracked_plan_ids:
                    tracked_plan_ids.add(plan_id)
                    temp = PetlibroScheduleEnableSwitch(
                        coordinator, device, plan_id, display_id
                    )
                    temp.entity_registry_enabled_default = False
                    new_switches.append(temp)

            if new_switches:
                async_add_entities(new_switches)

        # Initial population on startup
        async_add_dynamic_switches()

        # Listen for updates to catch schedule additions/deletions
        coordinator.async_add_listener(async_add_dynamic_switches)


class PetlibroPumpSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to control the water fountain pump or base device switch."""

    _attr_has_entity_name = True
    _attr_name = "Pump"
    _attr_icon = "mdi:pump"

    def __init__(
        self,
        coordinator: PetlibroCoordinator,
        entry: ConfigEntry,
        device,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{entry.data['petlibro_serial_number']}_pump"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._device.serial_number)},
            "name": self._device.name,
            "manufacturer": self._device.manufacturer,
            "model": self._device.model,
        }

    @property
    def is_on(self) -> bool:
        """Return true if the pump is on."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("is_pump_running", False)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("is_online", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        return {
            "water_level": self.coordinator.data.get("water_level", 0),
            "filter_life": self.coordinator.data.get("filter_life", 0),
            "is_low_water": self.coordinator.data.get("is_low_water", False),
            "needs_filter_change": self.coordinator.data.get(
                "needs_filter_change", False
            ),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the pump."""
        _LOGGER.info("Turning on pump")
        await self._device.start_pump()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the pump."""
        _LOGGER.info("Turning off pump")
        await self._device.stop_pump()
        await self.coordinator.async_request_refresh()


class PetlibroScheduleEnableSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable or disable an individual feeding schedule slot."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        device,
        plan_id: Any,
        display_id: int | None = None,
    ) -> None:
        """Initialize the schedule enable switch."""
        super().__init__(coordinator)
        self._device = device
        self._plan_id = plan_id
        self._display_id = display_id if display_id is not None else plan_id

        self._attr_unique_id = (
            f"{device.serial_number}_schedule_{plan_id}_enabled"
        )
        self._attr_icon = "mdi:calendar-check"

    @property
    def name(self) -> str:
        """Return the display name using the 1-based schedule index."""
        idx = get_plan_display_index(
            self._device, self._plan_id, self._display_id
        )
        return f"Schedule {idx} Enabled"

    @property
    def device_info(self) -> dict[str, Any]:
        """Link to the same physical device."""
        return {
            "identifiers": {(DOMAIN, self._device.serial_number)},
            "name": self._device.name,
            "manufacturer": self._device.manufacturer,
            "model": self._device.model,
        }

    def _get_plan(self) -> dict | None:
        plans = self._device.feeding_schedule.get("plans", [])
        for plan in plans:
            if plan.get("planId") == self._plan_id:
                return plan
        return None

    @property
    def available(self) -> bool:
        return super().available and self._get_plan() is not None

    @property
    def is_on(self) -> bool:
        """Return true if active (e.g. repeat days are populated)."""
        plan = self._get_plan()
        if plan:
            return len(plan.get("repeatDay", [])) > 0
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable schedule slot by restoring all days."""
        await self._set_enabled_state([1, 2, 3, 4, 5, 6, 7])

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable schedule slot by clearing repeat days."""
        await self._set_enabled_state([])

    async def _set_enabled_state(self, repeat_days: list[int]) -> None:
        plans = self._device.feeding_schedule.get("plans", [])
        for plan in plans:
            if plan.get("planId") == self._plan_id:
                plan["repeatDay"] = repeat_days
                break

        self._device._schedule.plans = []
        for plan_data in plans:
            self._device.add_feeding_plan(
                id=plan_data.get("planId"),
                time=plan_data.get("executionTime"),
                amount=plan_data.get("grainNum"),
                repeat_day=plan_data.get("repeatDay"),
            )
        await self._device.update_feeding_plan_service(self._device._schedule)
        await self.coordinator.async_request_refresh()
