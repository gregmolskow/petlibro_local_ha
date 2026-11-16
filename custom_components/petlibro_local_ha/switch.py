"""Switch platform for Petlibro water fountain integration."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import PetlibroCoordinator
from .shared_const import _LOGGER, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Petlibro switch from a config entry."""
    runtime_data = entry.runtime_data
    coordinator: PetlibroCoordinator = runtime_data["coordinator"]
    device = runtime_data["device"]

    async_add_entities(
        [PetlibroPumpSwitch(coordinator, entry, device)],
        update_before_add=True,
    )


class PetlibroPumpSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to control the water fountain pump."""

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
