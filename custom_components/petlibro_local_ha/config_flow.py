"""Configuration flow for Petlibro MQTT Home Assistant integration."""

from __future__ import annotations

import re
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .shared_const import _LOGGER, DEFAULT_SCAN_INTERVAL, DOMAIN, TZ_OFFSET

# Serial number validation pattern (alphanumeric, typically 12+ characters)
SERIAL_NUMBER_PATTERN = re.compile(r"^[A-Z0-9]{10,}$", re.IGNORECASE)

DEVICE_TYPES = [
    {"value": "feeder", "label": "Feeder (PLAF301)"},
    {"value": "fountain", "label": "Water Fountain (PLWF116)"},
]


class PetlibroConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Petlibro MQTT HA integration."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
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
                serial_number = user_input["petlibro_serial_number"].strip().upper()

                if not SERIAL_NUMBER_PATTERN.match(serial_number):
                    errors["petlibro_serial_number"] = "invalid_serial"
                else:
                    # Update with normalized serial number
                    user_input["petlibro_serial_number"] = serial_number

                    # Set unique ID based on serial number
                    await self.async_set_unique_id(serial_number)
                    self._abort_if_unique_id_configured()

                    # Get device type and name
                    device_type = user_input.get("petlibro_device_type", "feeder")
                    device_type_label = (
                        "Feeder" if device_type == "feeder" else "Water Fountain"
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
        data_schema = vol.Schema(
            {
                vol.Required("petlibro_device_type"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=DEVICE_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("petlibro_serial_number"): cv.string,
                vol.Optional(
                    "petlibro_device_name",
                    default="",
                ): cv.string,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "info": "Select your device type and enter the serial number found on the device."
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
        return PetlibroOptionsFlowHandler(config_entry)


class PetlibroOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for the Petlibro integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow.

        Args:
            config_entry: Config entry instance
        """
        self.config_entry = config_entry
        self.device_type = config_entry.data.get("petlibro_device_type", "feeder")
        self.feeding_schedules = []

        # Only load feeding schedules for feeders
        if self.device_type == "feeder":
            self._load_feeding_schedules()

    def _load_feeding_schedules(self) -> None:
        """Load existing feeding schedules from the device."""
        # Safety check for runtime_data
        if (
            not hasattr(self.config_entry, "runtime_data")
            or not self.config_entry.runtime_data
        ):
            _LOGGER.warning("Runtime data not available during options flow init")
            return

        try:
            runtime_data = self.config_entry.runtime_data
            feeder = runtime_data["device"]
            schedule = feeder.feeding_schedule
            _LOGGER.debug("Loaded existing schedule: %s", schedule)

            for plan in schedule.get("plans", []):
                # Get values with proper defaults
                utc_time_str = plan.get("executionTime")
                grain_num = plan.get("grainNum", 1)  # Default to 1 portion
                plan_id = plan.get("planId")

                # Skip invalid plans
                if not utc_time_str or not isinstance(utc_time_str, str):
                    _LOGGER.warning(
                        "Skipping plan with invalid executionTime: %s", plan
                    )
                    continue

                if grain_num is None or grain_num == 0:
                    _LOGGER.warning("Skipping plan with invalid grainNum: %s", plan)
                    continue

                # Convert UTC time to local time
                try:
                    hours, minutes = map(int, utc_time_str.split(":"))
                    local_hours = (hours + int(TZ_OFFSET)) % 24
                    local_time_str = f"{local_hours:02d}:{minutes:02d}"

                    _LOGGER.debug(
                        f"Converting: {utc_time_str} (UTC) -> {local_time_str} (local), offset={TZ_OFFSET}"
                    )
                except (ValueError, AttributeError) as e:
                    _LOGGER.warning("Error converting time %s: %s", utc_time_str, e)
                    continue

                self.feeding_schedules.append(
                    {
                        "time": local_time_str,
                        "portions": grain_num,
                        "planId": plan_id,
                    }
                )

            # Sort schedules by time
            self.feeding_schedules.sort(key=lambda x: x["time"])
            _LOGGER.debug("Initialized with schedules: %s", self.feeding_schedules)

        except Exception as e:
            _LOGGER.exception("Error loading feeding schedules: %s", e)
            self.feeding_schedules = []

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Manage the options - show menu.

        Args:
            user_input: User provided options

        Returns:
            FlowResult: Menu with options
        """
        # Show different menu options based on device type
        if self.device_type == "feeder":
            menu_options = ["manage_schedules", "other_settings"]
        else:
            menu_options = ["other_settings"]

        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_manage_schedules(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Manage feeding schedules.

        Returns:
            FlowResult: Menu for schedule management
        """
        menu_options = ["add_schedule"]

        # Add edit/delete options if schedules exist
        if self.feeding_schedules:
            menu_options.append("view_schedules")
            menu_options.append("edit_schedule")
            menu_options.append("delete_schedule")

        menu_options.append("done")

        return self.async_show_menu(
            step_id="manage_schedules", menu_options=menu_options
        )

    async def async_step_add_schedule(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Add a new feeding schedule.

        Args:
            user_input: User provided schedule data

        Returns:
            FlowResult: Form or redirect to menu
        """
        if user_input is not None:
            # Validate portions
            portions = user_input.get("portions", 1)
            if portions is None or portions < 1:
                portions = 1

            # Add the new schedule
            self.feeding_schedules.append(
                {
                    "time": user_input["time"],
                    "portions": portions,
                }
            )
            _LOGGER.debug(
                "Added schedule: time=%s, portions=%s",
                user_input["time"],
                portions,
            )
            return await self.async_step_manage_schedules()

        return self.async_show_form(
            step_id="add_schedule",
            data_schema=vol.Schema(
                {
                    vol.Required("time"): selector.TimeSelector(),
                    vol.Required("portions", default=1): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=10,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            description_placeholders={"info": "Set feeding time and portion count"},
        )

    async def async_step_edit_schedule(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Select a schedule to edit.

        Args:
            user_input: Selected schedule to edit

        Returns:
            FlowResult: Form or redirect to edit form
        """
        if user_input is not None:
            self.edit_index = int(user_input["schedule_to_edit"])
            return await self.async_step_edit_schedule_form()

        # Create options for schedule selection
        schedule_options = [
            {
                "value": str(i),
                "label": f"{s['time']} - {s['portions']} portion(s)",
            }
            for i, s in enumerate(self.feeding_schedules)
        ]

        return self.async_show_form(
            step_id="edit_schedule",
            data_schema=vol.Schema(
                {
                    vol.Required("schedule_to_edit"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=schedule_options, mode="dropdown"
                        )
                    ),
                }
            ),
        )

    async def async_step_edit_schedule_form(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Edit the selected schedule.

        Args:
            user_input: Updated schedule data

        Returns:
            FlowResult: Form or redirect to menu
        """
        if user_input is not None:
            # Update the schedule
            if 0 <= self.edit_index < len(self.feeding_schedules):
                original_plan_id = self.feeding_schedules[self.edit_index].get("planId")
                portions = user_input.get("portions", 1)
                if portions is None or portions < 1:
                    portions = 1

                self.feeding_schedules[self.edit_index] = {
                    "time": user_input["time"],
                    "portions": portions,
                    "planId": original_plan_id,
                }
                _LOGGER.debug(
                    "Updated schedule %s: %s",
                    self.edit_index,
                    self.feeding_schedules[self.edit_index],
                )
            self.edit_index = None
            return await self.async_step_manage_schedules()

        # Get current schedule values
        if self.edit_index is None or not (
            0 <= self.edit_index < len(self.feeding_schedules)
        ):
            return await self.async_step_manage_schedules()

        current_schedule = self.feeding_schedules[self.edit_index]

        return self.async_show_form(
            step_id="edit_schedule_form",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "time", default=current_schedule.get("time")
                    ): selector.TimeSelector(),
                    vol.Required("portions", default=1): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=10,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            description_placeholders={
                "info": "Update the feeding schedule",
                "schedule_number": str(self.edit_index + 1),
            },
        )

    async def async_step_view_schedules(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """View current feeding schedules.

        Args:
            user_input: User input (when back button is pressed)

        Returns:
            FlowResult: Form showing schedules or redirect back to menu
        """
        # If user submitted (pressed back), return to schedule management
        if user_input is not None:
            return await self.async_step_manage_schedules()

        # Format schedules for display
        schedule_text = "\n\n".join(
            [
                f"Schedule {i + 1}:\n  Time: {s['time']}\n  Portions: {s['portions']}"
                for i, s in enumerate(self.feeding_schedules)
            ]
        )

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
    ) -> FlowResult:
        """Delete a feeding schedule.

        Args:
            user_input: Selected schedule to delete

        Returns:
            FlowResult: Form or redirect to menu
        """
        if user_input is not None:
            schedule_index = int(user_input["schedule_to_delete"])
            if 0 <= schedule_index < len(self.feeding_schedules):
                deleted = self.feeding_schedules.pop(schedule_index)
                _LOGGER.debug("Deleted schedule: %s", deleted)
            return await self.async_step_manage_schedules()

        # Create options for schedule selection
        schedule_options = [
            {
                "value": str(i),
                "label": f"{s['time']} - {s['portions']} portion(s)",
            }
            for i, s in enumerate(self.feeding_schedules)
        ]

        return self.async_show_form(
            step_id="delete_schedule",
            data_schema=vol.Schema(
                {
                    vol.Required("schedule_to_delete"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=schedule_options, mode="dropdown"
                        )
                    ),
                }
            ),
        )

    async def async_step_done(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Finish schedule management.

        Returns:
            FlowResult: Create entry with all schedules
        """
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
    ) -> FlowResult:
        """Configure other settings like scan interval.

        Args:
            user_input: User provided settings

        Returns:
            FlowResult: Form or create entry
        """
        if user_input is not None:
            # Merge with existing feeding schedules
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
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "scan_interval",
                        default=current_scan_interval,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                }
            ),
            description_placeholders={
                "info": "Configure polling interval (minutes between status updates)"
            },
        )
