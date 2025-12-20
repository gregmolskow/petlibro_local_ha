"""Vacuum platform with MQTT support for My Integration."""

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,  # DOMAIN = "your_integration_name"
)
from .coordinator import PetlibroCoordinator
from .ha_plaf301 import PLAF301

PLATFORMS: list[str] = ["vacuum"]


async def async_setup_entry(  # noqa: RUF029
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):

    coordinator: PetlibroCoordinator = entry.runtime_data
    async_add_entities([coordinator.entity])
    hass.async_create_task(coordinator.feeder.start())


class PLAF301Entity(StateVacuumEntity, CoordinatorEntity):
    """MQTT-enabled robot vacuum for HA."""

    model: str = "PLAF301"
    _sn: str | None = None
    _attr_supported_features: VacuumEntityFeature = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.STATE
        | VacuumEntityFeature.BATTERY
        | VacuumEntityFeature.STATUS
        | VacuumEntityFeature.RETURN_HOME
    )
    """Supported features of the device"""
    _feeder: PLAF301 | None = None

    def __init__(
        self,
        hass,
        name: str,
        sn: str,
        coordinator: PetlibroCoordinator,
    ) -> None:
        """Initialize the vacuum entity."""
        CoordinatorEntity.__init__(self, coordinator)
        StateVacuumEntity.__init__(self)
        self._sn = sn.upper()
        self._attr_name = name
        self._attr_unique_id = f"{name}_{self._sn.lower()}"
        self._feeder = coordinator.feeder

    @property
    def activity(self) -> str:
        """Return the current activity of the vacuum."""
        return self.coordinator.data

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for device registry."""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},  # MUST match above
            "manufacturer": "Petlibro",
            "model": "PLAF301",
            "name": self._attr_name,
        }

    async def async_return_to_base(self, **kwargs: dict[str, Any]) -> None:
        """Toggle the cover state."""
        await self._feeder.toggle_cover()
        self.async_write_ha_state()

    async def async_start(self) -> None:
        """Run the main function of the feeder, dispense food."""
        self._is_on = True
        await self._feeder.dispense_food(1)
        self.async_write_ha_state()
