"""Sensor platform for Petlibro integration."""

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
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
    coordinator: PetlibroCoordinator = entry.runtime_data

    async_add_entities(
        [
            PLAF301ConnectivitySensor(coordinator, entry),
            # PLAF301RSSISensor(coordinator, entry),
            # PLAF301BatterySensor(coordinator, entry),
            PLAF301StatusSensor(coordinator, entry),
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
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data['petlibro_serial_number']}_status"
        self._attr_name = f"{entry.data['petlibro_device_name']} Status"
        self._feeder = coordinator.feeder

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
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{entry.data['petlibro_serial_number']}_last_heartbeat"
        )
        self._feeder = coordinator.feeder

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


class PLAF301RSSISensor(CoordinatorEntity, SensorEntity):
    """Sensor showing WiFi signal strength."""

    _attr_has_entity_name = True
    _attr_name = "WiFi Signal"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = "dBm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:wifi"

    def __init__(
        self,
        coordinator: PetlibroCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data['petlibro_serial_number']}_rssi"
        self._feeder = coordinator.feeder

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("rssi")

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


class PLAF301BatterySensor(CoordinatorEntity, SensorEntity):
    """Sensor showing battery level."""

    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: PetlibroCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data['petlibro_serial_number']}_battery"
        self._feeder = coordinator.feeder

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("battery_level")

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
