"""Sensor platform for Petlibro integration."""

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import PetlibroCoordinator
from .shared_const import DOMAIN, TZ


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Petlibro sensors from a config entry."""
    runtime_data = entry.runtime_data
    coordinator: PetlibroCoordinator = runtime_data["coordinator"]
    device = runtime_data["device"]

    async_add_entities(
        [
            PLAF301ConnectivitySensor(coordinator, entry, device),
            PLAF301StatusSensor(coordinator, entry, device),
        ],
        update_before_add=True,
    )


class PLAF301StatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing current device status/state."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:information-outline"

    def __init__(
        self,
        coordinator: PetlibroCoordinator,
        entry: ConfigEntry,
        device,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{entry.data['petlibro_serial_number']}_status"
        self._attr_name = "Status"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            value: str = "Unknown"
        # Check various states in priority order
        elif not self.coordinator.data.get("is_online", False):
            value = "Offline"
        elif self.coordinator.data.get("is_dispensing", False):
            value = "Dispensing"
        elif self.coordinator.data.get("is_door_opening", False):
            value = "Door Opening"
        elif self.coordinator.data.get("is_door_closing", False):
            value = "Door Closing"
        elif self.coordinator.data.get("is_empty", False):
            value = "Empty"
        elif self.coordinator.data.get("is_clogged", False):
            value = "Clogged"
        elif self.coordinator.data.get("is_door_open", False):
            value = "Door Open"
        else:
            value = "Idle"

        return value

    @property
    def icon(self):
        """Return icon based on state."""
        if not self.coordinator.data:
            return "mdi:help-circle-outline"

        status = self.native_value
        icon_map = {
            "Offline": "mdi:cloud-off-outline",
            "Dispensing": "mdi:food-drumstick",
            "Door Opening": "mdi:door-open",
            "Door Closing": "mdi:door-closed",
            "Empty": "mdi:alert-circle-outline",
            "Clogged": "mdi:alert-outline",
            "Door Open": "mdi:door-open",
            "Idle": "mdi:check-circle-outline",
        }
        return icon_map.get(status, "mdi:information-outline")

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        return {
            "error_code": self.coordinator.data.get("error_code", "none"),
            "state_code": self.coordinator.data.get("state"),
            "online": self.coordinator.data.get("is_online", False),
            "door_open": self.coordinator.data.get("is_door_open", False),
            "dispensing": self.coordinator.data.get("is_dispensing", False),
            "empty": self.coordinator.data.get("is_empty", False),
            "clogged": self.coordinator.data.get("is_clogged", False),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for device registry."""
        return {
            "identifiers": {(DOMAIN, self._device.serial_number)},
            "name": self._device.name,
            "manufacturer": self._device.manufacturer,
            "model": self._device.model,
            "sw_version": (
                self._device._startup_info.softwareVersion
                if self._device._startup_info.softwareVersion
                else None
            ),
        }


class PLAF301ConnectivitySensor(CoordinatorEntity, SensorEntity):
    """Sensor showing time since last heartbeat."""

    _attr_has_entity_name = True
    _attr_name = "Last Heartbeat"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:connection"

    def __init__(
        self,
        coordinator: PetlibroCoordinator,
        entry: ConfigEntry,
        device,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{entry.data['petlibro_serial_number']}_last_heartbeat"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        last_seen = self.coordinator.data.get("last_seen", 0)
        if last_seen > 0:
            return datetime.fromtimestamp(last_seen, TZ)
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for device registry."""
        return {
            "identifiers": {(DOMAIN, self._device.serial_number)},
            "name": self._device.name,
            "manufacturer": self._device.manufacturer,
            "model": self._device.model,
            "sw_version": (
                self._device._startup_info.softwareVersion
                if self._device._startup_info.softwareVersion
                else None
            ),
        }
