"""Sensor platform for Petlibro integration."""

from datetime import datetime, timedelta, timezone
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
from .shared_const import DOMAIN, TZ, utc_to_local_time

DAY_NAMES = {
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}


def format_repeat_days(repeat_days: list[int] | None) -> str:
    """Format repeatDay list into a friendly string."""
    if not repeat_days:
        return "Daily"
    sorted_days = sorted(set(repeat_days))
    if sorted_days == [1, 2, 3, 4, 5, 6, 7]:
        return "Daily"
    if sorted_days == [1, 2, 3, 4, 5]:
        return "Weekdays"
    if sorted_days == [6, 7]:
        return "Weekends"
    return ", ".join(DAY_NAMES.get(d, str(d)) for d in sorted_days)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Petlibro sensors from a config entry."""
    runtime_data = entry.runtime_data
    coordinator: PetlibroCoordinator = runtime_data["coordinator"]
    device_type: str = runtime_data.get("device_type", "feeder")

    entities: list[SensorEntity] = []

    if device_type == "feeder":
        entities.extend([
            PLAF301ConnectivitySensor(coordinator, entry),
            PLAF301StatusSensor(coordinator, entry),
            PLAF301NextMealSensor(coordinator, entry),
        ])

    async_add_entities(entities, update_before_add=True)


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
            return "Unknown"

        # Check various states in priority order
        if not self.coordinator.data.get("is_online", False):
            return "Offline"
        if self.coordinator.data.get("is_dispensing", False):
            return "Dispensing"
        if self.coordinator.data.get("is_door_opening", False):
            return "Door Opening"
        if self.coordinator.data.get("is_door_closing", False):
            return "Door Closing"
        if self.coordinator.data.get("is_empty", False):
            return "Empty"
        if self.coordinator.data.get("is_clogged", False):
            return "Clogged"
        if self.coordinator.data.get("is_door_open", False):
            return "Door Open"
        return "Idle"

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
        self._attr_unique_id = (
            f"{entry.data['petlibro_serial_number']}_battery"
        )
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


class PLAF301NextMealSensor(CoordinatorEntity, SensorEntity):
    """Sensor displaying the next scheduled meal timestamp and active schedules."""

    _attr_has_entity_name = True
    _attr_name = "Next Scheduled Meal"
    _attr_translation_key = "next_meal"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: PetlibroCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{entry.data['petlibro_serial_number']}_next_meal"
        )
        self._feeder = coordinator.feeder

    def _get_next_meal(self) -> tuple[datetime | None, dict[str, Any] | None]:
        """Calculate the next meal datetime and plan."""
        plans = (self.coordinator.data or {}).get("feeding_plans", [])
        if not plans:
            return None, None

        now = datetime.now(timezone.utc)
        candidates: list[tuple[datetime, dict[str, Any]]] = []

        for plan in plans:
            if isinstance(plan, dict):
                exec_time = plan.get("executionTime")
                repeat_day = plan.get("repeatDay") or [1, 2, 3, 4, 5, 6, 7]
            else:
                exec_time = getattr(plan, "executionTime", "")
                repeat_day = getattr(plan, "repeatDay", None) or [
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                ]

            if not exec_time or ":" not in str(exec_time):
                continue

            try:
                parts = str(exec_time).split(":")
                h, m = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                continue

            for day_offset in range(8):
                candidate_date = now.date() + timedelta(days=day_offset)
                pl_day = candidate_date.weekday() + 1
                if pl_day not in repeat_day:
                    continue

                candidate = datetime(
                    candidate_date.year,
                    candidate_date.month,
                    candidate_date.day,
                    h,
                    m,
                    tzinfo=timezone.utc,
                )
                if candidate > now:
                    p_dict = (
                        plan if isinstance(plan, dict) else plan.to_dict()
                    )
                    candidates.append((candidate, p_dict))
                    break

        if not candidates:
            return None, None

        return min(candidates, key=lambda x: x[0])

    @property
    def native_value(self) -> datetime | None:
        """Return timestamp of next meal."""
        next_dt, _ = self._get_next_meal()
        return next_dt

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes about schedules and next meal."""
        next_dt, next_plan = self._get_next_meal()
        plans = (self.coordinator.data or {}).get("feeding_plans", [])

        formatted_schedules: list[dict[str, Any]] = []
        summary_lines: list[str] = []
        total_daily_portions = 0

        for idx, plan in enumerate(plans):
            p_dict = plan if isinstance(plan, dict) else plan.to_dict()
            utc_time = p_dict.get("executionTime", "")
            portions = p_dict.get("grainNum", 1)
            raw_days = p_dict.get("repeatDay") or [1, 2, 3, 4, 5, 6, 7]
            plan_id = p_dict.get("planId", idx + 1)

            if utc_time and ":" in utc_time:
                try:
                    local_time, local_days = utc_to_local_time(
                        utc_time, raw_days
                    )
                except Exception:
                    local_time = utc_time
                    local_days = raw_days
            else:
                local_time = utc_time
                local_days = raw_days

            days_str = format_repeat_days(local_days)
            portion_str = (
                f"{portions} portion"
                if portions == 1
                else f"{portions} portions"
            )

            formatted_schedules.append({
                "plan_id": plan_id,
                "time": local_time,
                "utc_time": utc_time,
                "portions": portions,
                "days": days_str,
                "repeat_day": local_days,
            })
            summary_lines.append(f"• {local_time} - {portion_str} ({days_str})")
            total_daily_portions += portions

        formatted_schedules.sort(key=lambda x: x.get("time", ""))

        attrs: dict[str, Any] = {
            "total_plans": len(plans),
            "total_daily_portions": total_daily_portions,
            "schedules": formatted_schedules,
            "schedule_summary": (
                "\n".join(summary_lines)
                if summary_lines
                else "No schedules configured"
            ),
        }

        if next_plan and next_dt:
            next_utc = next_plan.get("executionTime", "")
            next_days = next_plan.get("repeatDay") or [1, 2, 3, 4, 5, 6, 7]
            try:
                next_local_time, _ = utc_to_local_time(next_utc, next_days)
            except Exception:
                next_local_time = next_utc

            attrs["next_meal_time"] = next_local_time
            attrs["next_meal_portions"] = next_plan.get("grainNum", 1)
            attrs["next_meal_plan_id"] = next_plan.get("planId")

        return attrs

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for device registry."""
        return {
            "identifiers": {(DOMAIN, self._feeder.serial_number)},
            "name": self._feeder.name,
            "manufacturer": self._feeder.manufacturer,
            "model": self._feeder.model,
            "sw_version": (
                self._feeder._startup_info.softwareVersion
                if self._feeder._startup_info.softwareVersion
                else None
            ),
        }
