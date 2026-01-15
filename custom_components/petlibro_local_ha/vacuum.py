"""Vacuum platform for Petlibro integration."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .shared_const import _LOGGER, DOMAIN, TZ

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
        # | VacuumEntityFeature.RETURN_HOME
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
    def available(self) -> bool:
        """Return True if entity is available."""
        # Device is available if coordinator has data and device is online
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("is_online", False)

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

        ts = datetime.fromtimestamp(datetime.now(TZ).timestamp(), TZ).strftime(
            "%d/%m/%Y %H:%M:%S"
        )

        # Get last seen timestamp
        last_seen_ts = self.coordinator.data.get("last_seen", 0)
        if last_seen_ts > 0:
            last_seen = datetime.fromtimestamp(last_seen_ts, TZ).strftime(
                "%d/%m/%Y %H:%M:%S"
            )
        else:
            last_seen = "Never"

        seconds_since = self.coordinator.data.get("seconds_since_heartbeat", -1)
        if seconds_since >= 0:
            minutes_since = seconds_since // 60
            time_since = f"{minutes_since}m {seconds_since % 60}s ago"
        else:
            time_since = "Unknown"

        # Determine door status string
        if self.coordinator.data.get("is_door_opening", False):
            door_status = "Opening"
        elif self.coordinator.data.get("is_door_closing", False):
            door_status = "Closing"
        elif self.coordinator.data.get("is_door_open", False):
            door_status = "Open"
        else:
            door_status = "Closed"

        return {
            "door_open": self.coordinator.data.get("is_door_open", False),
            "door_status": door_status,  # <-- ADD THIS
            "dispensing": self.coordinator.data.get("is_dispensing", False),
            "empty": self.coordinator.data.get("is_empty", False),
            "clogged": self.coordinator.data.get("is_clogged", False),
            "error": self.coordinator.data.get("error_code", "none"),
            "online": self.coordinator.data.get("is_online", False),
            "last_seen": last_seen,
            "time_since_heartbeat": time_since,
            "Last Update": ts,
            "Battery": self.coordinator.data.get("battery_level"),
            "RSSI": self.coordinator.data.get("rssi"),
        }

    async def async_start(self) -> None:
        """Start the vacuum (dispense food)."""
        _LOGGER.info("Starting vacuum (dispensing food)")
        await self._feeder.dispense_food(1)
        await self.coordinator.async_request_refresh()

    # async def async_return_to_base(self, **kwargs: Any) -> None:
    #     """Return to base (toggle door)."""
    #     _LOGGER.info("Returning to base (toggling door)")
    #     await self._feeder.toggle_door()
    #     await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.info("Petlibro vacuum entity added: %s", self._attr_name)
