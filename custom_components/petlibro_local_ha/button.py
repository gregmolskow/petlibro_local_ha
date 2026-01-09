"""Button platform for Petlibro integration."""

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import _LOGGER, DOMAIN
from .coordinator import PetlibroCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Petlibro button from a config entry."""
    coordinator: PetlibroCoordinator = entry.runtime_data

    async_add_entities(
        [PetlibroDispenseButton(coordinator, entry, portions=1)],
        update_before_add=True,
    )


class PetlibroDispenseButton(CoordinatorEntity, ButtonEntity):
    """Button to dispense food from the Petlibro feeder."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PetlibroCoordinator,
        entry: ConfigEntry,
        portions: int = 1,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator)
        self._portions = portions
        self._feeder = coordinator.feeder

        # Set unique ID and name based on portions
        self._attr_unique_id = (
            f"{entry.data['petlibro_serial_number']}_dispense_{portions}"
        )

        if portions == 1:
            self._attr_name = "Dispense Food"
            self._attr_icon = "mdi:bowl"
        else:
            self._attr_name = f"Dispense {portions} Portions"
            self._attr_icon = "mdi:bowl-outline"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._feeder.serial_number)},
            "name": self._feeder.name,
            "manufacturer": self._feeder.manufacturer,
            "model": self._feeder.model,
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("is_online", False)

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Dispensing %s portion(s) via button press", self._portions)
        await self._feeder.dispense_food(self._portions)
        await self.coordinator.async_request_refresh()
