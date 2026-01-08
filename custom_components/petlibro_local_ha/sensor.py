"""Sensor platform for Petlibro integration."""

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import TZ
from .coordinator import PetlibroCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Petlibro sensors from a config entry."""
    coordinator: PetlibroCoordinator = entry.runtime_data

    async_add_entities(
        [
            PetlibroConnectivitySensor(coordinator, entry),
            PetlibroRSSISensor(coordinator, entry),
            PetlibroBatterySensor(coordinator, entry),
        ],
        update_before_add=True,
    )


class PetlibroConnectivitySensor(CoordinatorEntity, SensorEntity):
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


class PetlibroRSSISensor(CoordinatorEntity, SensorEntity):
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

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("rssi")


class PetlibroBatterySensor(CoordinatorEntity, SensorEntity):
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

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("battery_level")
