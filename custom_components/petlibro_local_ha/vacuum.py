"""Vacuum platform for Petlibro integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import _LOGGER, DOMAIN, TZ, datetime
from .message_data import FEEDING_PLAN_SERVICE, FoodPlan

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PetlibroCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Petlibro vacuum from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities
    """
    coordinator: PetlibroCoordinator = entry.runtime_data
    feeding_plan = FEEDING_PLAN_SERVICE()
    feeding_schedules = entry.options.get("feeding_schedules", [])
    for i, schedule in enumerate(feeding_schedules):
        food_plan = FoodPlan(
            grainNum=schedule["portions"],
            executionTime=schedule["time"],
            planId=i,
        )
        feeding_plan.add_plan(food_plan)

    if feeding_schedules:
        coordinator.feeder.update_feeding_plan_service(feeding_plan)
    # @callback
    # def schedule_changed(event):
    #     """Handle schedule state changes."""
    #     new_state = event.data.get("new_state")
    #     if new_state and new_state.state == "on":
    #         # Schedule is active - start vacuum
    #         hass.async_create_task(
    #             hass.services.async_call(
    #                 "vacuum",
    #                 "start",
    #                 {"entity_id": entry.data["petlibro_serial_number"]},
    #             )
    #         )

    # # Listen for schedule changes
    # entry.async_on_unload(
    #     async_track_state_change_event(
    #         hass, schedule_entity_id, schedule_changed
    #     )
    # )

    async_add_entities(
        [PetlibroVacuumEntity(coordinator, entry)],
        update_before_add=True,
    )


class PetlibroVacuumEntity(CoordinatorEntity, StateVacuumEntity):
    """Representation of a Petlibro feeder as a vacuum entity."""

    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.STATE
        | VacuumEntityFeature.BATTERY
        | VacuumEntityFeature.STATUS
        | VacuumEntityFeature.RETURN_HOME
    )
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PetlibroCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the vacuum entity.

        Args:
            coordinator: Data coordinator
            entry: Config entry
        """
        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.data['petlibro_serial_number']}_vacuum"
        self._attr_name = "Feeder"

        self.coordinator: PetlibroCoordinator = coordinator
        self._feeder = coordinator.feeder

        # Extract feed plans from entry options, assuming an unordered dictionary
        plans: dict[int, dict[str, int]] = {}
        for key in entry.options:
            if key.startswith("feed_"):
                if "portions" in key:
                    plans[int(key.split("_")[1])]["portions"] = entry.options[
                        key
                    ]
                elif "time" in key:
                    plans[int(key.split("_")[1])]["time"] = entry.options[key]

        for item in plans:
            self._feeder.add_feeding_plan(
                item,
                executionTime=plans[item]["time"],
                grainNum=plans[item]["portions"],
            )

        self._feeder.hass.async_create_task(
            self.coordinator.async_request_refresh()
        )

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for device registry."""
        return {
            "identifiers": {(DOMAIN, self._feeder.serial_number)},
            "name": self._attr_name,
            "manufacturer": self._feeder.manufacturer,
            "model": self._feeder.model,
            "sw_version": (
                self._feeder._startup_info.softwareVersion
                if self._feeder._startup_info.softwareVersion
                else None
            ),
        }

    @property
    def activity(self) -> str | None:
        """Return the current activity of the vacuum."""
        if self.coordinator.data:
            return self.coordinator.data.get("activity")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        ts = datetime.fromtimestamp(datetime.now(TZ).timestamp()).strftime(
            "%d/%m/%Y %H:%M:%S"
        )
        return {
            "door_open": self.coordinator.data.get("is_door_open", False),
            "dispensing": self.coordinator.data.get("is_dispensing", False),
            "empty": self.coordinator.data.get("is_empty", False),
            "clogged": self.coordinator.data.get("is_clogged", False),
            "error": self.coordinator.data.get("error_code", "none"),
            "Last Update": ts,
            "Battery": self.coordinator.data.get("battery_level"),
            "RSSI": self.coordinator.data.get("rssi"),
        }

    async def async_start(self) -> None:
        """Start the vacuum (dispense food)."""
        _LOGGER.info("Starting vacuum (dispensing food)")
        await self._feeder.dispense_food(1)
        await self.coordinator.async_request_refresh()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Return to base (toggle door)."""
        _LOGGER.info("Returning to base (toggling door)")
        await self._feeder.toggle_door()
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.info("Petlibro vacuum entity added: %s", self._attr_name)
