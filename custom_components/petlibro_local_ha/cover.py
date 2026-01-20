"""Cover platform for Petlibro integration."""

from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
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
    """Set up Petlibro cover from a config entry."""
    runtime_data = entry.runtime_data
    coordinator: PetlibroCoordinator = runtime_data["coordinator"]
    device = runtime_data["device"]

    async_add_entities(
        [PLAF301CoverEntity(coordinator, entry, device)],
        update_before_add=True,
    )


class PLAF301CoverEntity(CoordinatorEntity, CoverEntity):
    """Representation of a Petlibro feeder barn door as a cover entity."""

    _attr_has_entity_name = True
    _attr_name = "Food Cover"
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
    )

    def __init__(
        self,
        coordinator: PetlibroCoordinator,
        entry: ConfigEntry,
        device,
    ) -> None:
        """Initialize the cover entity."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{entry.data['petlibro_serial_number']}_cover"

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
    def is_closed(self) -> bool:
        """Return if the cover is closed."""
        if not self.coordinator.data:
            return None
        # Door is closed when is_door_open is False
        return not self.coordinator.data.get("is_door_open", False)

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("is_door_opening", False)

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("is_door_closing", False)

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
            "is_opening": self.is_opening,
            "is_closing": self.is_closing,
        }

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover (barn door)."""
        _LOGGER.info("Opening barn door")
        await self._device.open_door()
        # Request immediate refresh to show opening state
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover (barn door)."""
        _LOGGER.info("Closing barn door")
        await self._device.close_door()
        # Request immediate refresh to show closing state
        await self.coordinator.async_request_refresh()
