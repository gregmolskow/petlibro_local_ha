"""Configuration flow for Petlibro MQTT Home Assistant integration."""

from __future__ import annotations

import re
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .schedule_helpers import (
    MAX_PORTIONS,
    MIN_PORTIONS,
    ScheduleValidationError,
    check_duplicate_schedule,
    check_max_schedules,
    validate_portions,
    validate_repeat_days,
    validate_time_string,
)
from .shared_const import (
    _LOGGER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    utc_to_local_time,
)

# Serial number validation pattern (alphanumeric, typically 12+ characters)
SERIAL_NUMBER_PATTERN = re.compile(r"^[A-Z0-9]{10,}$", re.IGNORECASE)

DEVICE_TYPES = [
    {"value": "auto", "label": "Auto-detect from serial number"},
    {"value": "feeder", "label": "Feeder (PLAF301)"},
    {"value": "fountain", "label": "Water Fountain (PLWF116)"},
]

DAY_OPTIONS = [
    {"value": "1", "label": "Monday"},
    {"value": "2", "label": "Tuesday"},
    {"value": "3", "label": "Wednesday"},
    {"value": "4", "label": "Thursday"},
    {"value": "5", "label": "Friday"},
    {"value": "6", "label": "Saturday"},
    {"value": "7", "label": "Sunday"},
]

_DAY_SHORT = {
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}

ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]


def _format_days(repeat_days: list[int] | None) -> str:
    """Format repeatDay list into a human-readable string."""
    if not repeat_days:
        return "Daily"
    sorted_days = sorted(set(repeat_days))
    if sorted_days == ALL_DAYS:
        return "Daily"
    if sorted_days == [1, 2, 3, 4, 5]:
        return "Weekdays"
    if sorted_days == [6, 7]:
        return "Weekends"
    return ", ".join(_DAY_SHORT.get(d, str(d)) for d in sorted_days)


def detect_device_type(serial_number: str) -> str:
    """Detect device type from serial number prefix.

    Args:
        serial_number: Device serial number

    Returns:
        Device type: "feeder" or "fountain"
    """
    sn_upper = serial_number.upper()

    if sn_upper.startswith("AF"):
        return "feeder"
    if sn_upper.startswith("WF"):
        return "fountain"
    # Default to feeder for backward compatibility
    _LOGGER.warning(
        "Unknown serial number prefix for %s, defaulting to feeder",
        serial_number,
    )
    return "feeder"


class PetlibroConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Petlibro MQTT HA integration."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step.

        Args:
            user_input: User provided configuration

        Returns:
            FlowResult: Either form or create entry
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Validate and normalize serial number
                serial_number = (
                    user_input["petlibro_serial_number"].strip().upper()
                )

                if not SERIAL_NUMBER_PATTERN.match(serial_number):
                    errors["petlibro_serial_number"] = "invalid_serial"
                else:
                    # Update with normalized serial number
                    user_input["petlibro_serial_number"] = serial_number

                    # Set unique ID based on serial number
                    await self.async_set_unique_id(serial_number)
                    self._abort_if_unique_id_configured()

                    # Get device type - auto-detect if set to "auto"
                    device_type_input = user_input.get(
                        "petlibro_device_type", "auto"
                    )

                    if device_type_input == "auto":
                        device_type = detect_device_type(serial_number)
                        _LOGGER.info(
                            "Auto-detected device type '%s' from serial number %s",
                            device_type,
                            serial_number,
                        )
                        # Don't store "auto", store the detected type
                        user_input["petlibro_device_type"] = device_type
                    else:
                        device_type = device_type_input

                    device_type_label = (
                        "Feeder"
                        if device_type == "feeder"
                        else "Water Fountain"
                    )

                    # Create entry
                    title = user_input.get(
                        "petlibro_device_name",
                        f"Petlibro {device_type_label} {serial_number[:6]}",
                    )

                    return self.async_create_entry(
                        title=title,
                        data=user_input,
                    )

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error in config flow")
                errors["base"] = "unknown"

        # Build schema
        data_schema = vol.Schema({
            vol.Required("petlibro_serial_number"): cv.string,
            vol.Optional(
                "petlibro_device_type", default="auto"
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=DEVICE_TYPES,  # type: ignore
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                "petlibro_device_name",
                default="",
            ): cv.string,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "info": "Enter the serial number found on your device. The device type will be auto-detected from the serial number prefix (AF=Feeder, WF=Fountain)."
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PetlibroOptionsFlowHandler:
        """Get the options flow for this handler.

        Args:
            config_entry: Config entry instance

        Returns:
            Options flow handler
        """
        return PetlibroOptionsFlowHandler()


class PetlibroOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for the Petlibro integration."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self.feeding_schedules: list[dict[str, Any]] = []
        self.edit_index: int | None = None
        self._schedules_loaded: bool = False

    @property
    def device_type(self) -> str:
        """Return the device type."""
        return self.config_entry.data.get("petlibro_device_type", "feeder")

    def _load_feeding_schedules(self) -> None:
        """Load existing feeding schedules from the device (falling back to options)."""
        plans: list[dict[str, Any]] = []
        runtime_data = getattr(self.config_entry, "runtime_data", None)
        if runtime_data:
            feeder = runtime_data["device"]
            plans = feeder.feeding_schedule.get("plans", [])

        if plans:
            for plan in plans:
                utc_time_str = plan.get("executionTime")
                grain_num = plan.get("grainNum", 1)
                plan_id = plan.get("planId")
                if not utc_time_str or not isinstance(utc_time_str, str):
                    continue
                if grain_num is None or grain_num == 0:
                    grain_num = 1

                repeat_days = plan.get("repeatDay")
                if repeat_days is None:
                    repeat_days = ALL_DAYS

                try:
                    local_time_str, local_days = utc_to_local_time(
                        utc_time_str, repeat_days
                    )
                except (ValueError, AttributeError) as err:
                    _LOGGER.warning(
                        "Error converting time %s: %s", utc_time_str, err
                    )
                    continue

                entry: dict[str, Any] = {
                    "time": local_time_str,
                    "portions": grain_num,
                    "repeatDay": local_days,
                }
                if plan_id is not None:
                    entry["planId"] = plan_id
                self.feeding_schedules.append(entry)
        else:
            for sched in self.config_entry.options.get(
                "feeding_schedules", []
            ):
                self.feeding_schedules.append(dict(sched))

        self.feeding_schedules.sort(key=lambda x: x["time"])

    def _schedule_dropdown_options(self) -> list[dict[str, str]]:
        """Build dropdown options for edit/delete schedule selectors."""
        return [
            {
                "value": str(i),
                "label": (
                    f"{s['time']} - {s['portions']} portion(s) "
                    f"({_format_days(s.get('repeatDay'))})"
                ),
            }
            for i, s in enumerate(self.feeding_schedules)
        ]

    def _schedule_form_schema(
        self,
        default_time: str | None = None,
        default_portions: int = 1,
        default_days: list[str] | None = None,
    ) -> vol.Schema:
        """Build the form schema for adding or editing a schedule."""
        time_key = (
            vol.Required("time", default=default_time)
            if default_time
            else vol.Required("time")
        )
        return vol.Schema({
            time_key: selector.TimeSelector(),
            vol.Optional(
                "days",
                default=default_days if default_days is not None else [],
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=DAY_OPTIONS,  # type: ignore[arg-type]
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                "portions", default=default_portions
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_PORTIONS,
                    max=MAX_PORTIONS,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        })

    def _validate_schedule_input(
        self,
        user_input: dict[str, Any],
        *,
        exclude_index: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Validate add/edit schedule form input."""
        errors: dict[str, str] = {}
        try:
            time_str = validate_time_string(user_input.get("time", ""))
        except ScheduleValidationError:
            errors["time"] = "invalid_time"
            return None, errors

        try:
            portions = validate_portions(user_input.get("portions", 1))
        except ScheduleValidationError:
            portions = MIN_PORTIONS

        raw_days = user_input.get("days")
        days = validate_repeat_days(raw_days or None)

        if exclude_index is None:
            max_err = check_max_schedules(self.feeding_schedules, adding=1)
            if max_err:
                errors["base"] = "too_many_schedules"
                return None, errors

        dup_err = check_duplicate_schedule(
            time_str,
            days,
            self.feeding_schedules,
            exclude_index=exclude_index,
        )
        if dup_err:
            errors["time"] = "duplicate_schedule"
            return None, errors

        return {
            "time": time_str,
            "portions": portions,
            "repeatDay": days,
        }, errors

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage the options - show menu for feeders or settings for fountains."""
        if not self._schedules_loaded:
            if self.device_type == "feeder":
                self._load_feeding_schedules()
            self._schedules_loaded = True

        if self.device_type == "feeder":
            return self.async_show_menu(
                step_id="init",
                menu_options=["manage_schedules", "other_settings"],
            )

        return await self.async_step_other_settings()

    async def async_step_manage_schedules(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Show feeding schedule management menu."""
        menu_options = ["add_schedule"]

        if self.feeding_schedules:
            menu_options.extend([
                "view_schedules",
                "edit_schedule",
                "delete_schedule",
            ])

        menu_options.append("done")

        return self.async_show_menu(
            step_id="manage_schedules", menu_options=menu_options
        )

    async def async_step_add_schedule(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Add a new feeding schedule."""
        errors: dict[str, str] = {}

        if user_input is not None:
            new_schedule, errors = self._validate_schedule_input(user_input)
            if new_schedule is not None:
                self.feeding_schedules.append(new_schedule)
                self.feeding_schedules.sort(key=lambda x: x["time"])
                _LOGGER.debug("Added schedule: %s", new_schedule)
                return await self.async_step_manage_schedules()

        return self.async_show_form(
            step_id="add_schedule",
            data_schema=self._schedule_form_schema(),
            errors=errors,
            description_placeholders={
                "info": "Set feeding time, days, and portion count"
            },
        )

    async def async_step_edit_schedule(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select a schedule to edit."""
        if user_input is not None:
            self.edit_index = int(user_input["schedule_to_edit"])
            return await self.async_step_edit_schedule_form()

        return self.async_show_form(
            step_id="edit_schedule",
            data_schema=vol.Schema({
                vol.Required("schedule_to_edit"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._schedule_dropdown_options(),  # type: ignore[arg-type]
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
        )

    async def async_step_edit_schedule_form(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Edit the selected schedule."""
        if self.edit_index is None or not (
            0 <= self.edit_index < len(self.feeding_schedules)
        ):
            return await self.async_step_manage_schedules()

        errors: dict[str, str] = {}

        if user_input is not None:
            updated, errors = self._validate_schedule_input(
                user_input, exclude_index=self.edit_index
            )
            if updated is not None:
                original_plan_id = self.feeding_schedules[self.edit_index].get(
                    "planId"
                )
                if original_plan_id is not None:
                    updated["planId"] = original_plan_id
                self.feeding_schedules[self.edit_index] = updated
                self.feeding_schedules.sort(key=lambda x: x["time"])
                self.edit_index = None
                return await self.async_step_manage_schedules()

        current = self.feeding_schedules[self.edit_index]
        current_days = [
            str(d) for d in (current.get("repeatDay") or ALL_DAYS)
        ]

        return self.async_show_form(
            step_id="edit_schedule_form",
            data_schema=self._schedule_form_schema(
                default_time=current.get("time"),
                default_portions=current.get("portions", 1),
                default_days=current_days,
            ),
            errors=errors,
            description_placeholders={
                "info": "Update the feeding schedule",
                "schedule_number": str(self.edit_index + 1),
            },
        )

    async def async_step_view_schedules(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """View current feeding schedules."""
        if user_input is not None:
            return await self.async_step_manage_schedules()

        schedule_text = "\n\n".join([
            (
                f"Schedule {i + 1}:\n"
                f"  Time: {s['time']}\n"
                f"  Portions: {s['portions']}\n"
                f"  Days: {_format_days(s.get('repeatDay'))}"
            )
            for i, s in enumerate(self.feeding_schedules)
        ])

        return self.async_show_form(
            step_id="view_schedules",
            data_schema=vol.Schema({}),
            description_placeholders={
                "schedules": schedule_text or "No schedules configured"
            },
        )

    async def async_step_delete_schedule(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Delete a feeding schedule."""
        if user_input is not None:
            schedule_index = int(user_input["schedule_to_delete"])
            if 0 <= schedule_index < len(self.feeding_schedules):
                deleted = self.feeding_schedules.pop(schedule_index)
                _LOGGER.debug("Deleted schedule: %s", deleted)
            return await self.async_step_manage_schedules()

        return self.async_show_form(
            step_id="delete_schedule",
            data_schema=vol.Schema({
                vol.Required("schedule_to_delete"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._schedule_dropdown_options(),  # type: ignore[arg-type]
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
        )

    async def async_step_done(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Finish schedule management and save options."""
        _LOGGER.debug("Saving feeding schedules: %s", self.feeding_schedules)

        return self.async_create_entry(
            title="",
            data={
                "feeding_schedules": self.feeding_schedules,
                "scan_interval": self.config_entry.options.get(
                    "scan_interval", DEFAULT_SCAN_INTERVAL
                ),
            },
        )

    async def async_step_other_settings(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure other settings like scan interval."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    "feeding_schedules": self.feeding_schedules,
                    "scan_interval": user_input.get(
                        "scan_interval", DEFAULT_SCAN_INTERVAL
                    ),
                },
            )

        current_scan_interval = self.config_entry.options.get(
            "scan_interval",
            DEFAULT_SCAN_INTERVAL,
        )

        return self.async_show_form(
            step_id="other_settings",
            data_schema=vol.Schema({
                vol.Optional(
                    "scan_interval",
                    default=current_scan_interval,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            }),
            description_placeholders={
                "info": "Configure polling interval (minutes between status updates)"
            },
        )
