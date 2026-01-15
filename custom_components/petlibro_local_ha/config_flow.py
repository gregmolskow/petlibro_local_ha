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

                    # Create entry
                    title = user_input.get(
                        "petlibro_device_name",
                        f"Petlibro {serial_number[:6]}",
                    )

                    return self.async_create_entry(
                        title=title,
                        data=user_input,
                    )

            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        # Build schema
        data_schema = vol.Schema({
            vol.Required("petlibro_serial_number"): cv.string,
            vol.Optional(
                "petlibro_device_name",
                default="Petlibro Feeder",
            ): cv.string,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
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
        schedule = config_entry.runtime_data.feeder.feeding_schedule  # type: ignore[union-attr]
        _LOGGER.debug("Loaded existing schedule: %s", schedule)
        self.feeding_schedules = []
        for plan in schedule.get("plans", []):
            utc_time_str = plan.get("executionTime")
            if utc_time_str:
                hours, minutes = map(int, utc_time_str.split(":"))

                # Convert UTC to local by adding timezone offset
                local_hours = (hours + int(TZ_OFFSET)) % 24
                local_time_str = f"{local_hours:02d}:{minutes:02d}"

                _LOGGER.debug(
                    f"Converting: {utc_time_str} (UTC) -> {local_time_str} (local), offset={TZ_OFFSET}"
                )
            else:
                local_time_str = utc_time_str
            self.feeding_schedules.append({
                "time": local_time_str,
                "portions": plan.get("grainNum"),
                "planId": plan.get("planId"),
            })

        self.feeding_schedules.sort(key=lambda x: x["time"])

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
        return self.async_show_menu(
            step_id="init", menu_options=["manage_schedules", "other_settings"]
        )

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
            # Add the new schedule
            self.feeding_schedules.append({
                "time": user_input["time"],
                "portions": user_input["portions"],
            })
            return await self.async_step_manage_schedules()

        return self.async_show_form(
            step_id="add_schedule",
            data_schema=vol.Schema({
                vol.Required("time"): selector.TimeSelector(),
                # vol.Optional("days"): selector.SelectSelector(
                #     selector.SelectSelectorConfig(
                #         options=[
                #             {"value": "mon", "label": "Monday"},
                #             {"value": "tue", "label": "Tuesday"},
                #             {"value": "wed", "label": "Wednesday"},
                #             {"value": "thu", "label": "Thursday"},
                #             {"value": "fri", "label": "Friday"},
                #             {"value": "sat", "label": "Saturday"},
                #             {"value": "sun", "label": "Sunday"},
                #         ],
                #         multiple=True,
                #         mode="dropdown",
                #     )
                # ),
                vol.Required("portions", default=1): int,
            }),
            description_placeholders={
                "info": "Leave days empty to feed every day"
            },
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
                "label": f"{s['time']} - {s['portions']} portion(s) - {', '.join(s.get('days', [])) if s.get('days') else 'Every day'}",
            }
            for i, s in enumerate(self.feeding_schedules)
        ]

        return self.async_show_form(
            step_id="edit_schedule",
            data_schema=vol.Schema({
                vol.Required("schedule_to_edit"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=schedule_options, mode="dropdown"
                    )
                ),
            }),
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
                original_plan_id = self.feeding_schedules[self.edit_index].get(
                    "planId"
                )
                self.feeding_schedules[self.edit_index] = {
                    "time": user_input["time"],
                    "portions": user_input["portions"],
                    "planId": original_plan_id,
                }
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
            data_schema=vol.Schema({
                vol.Required(
                    "time", default=current_schedule.get("time")
                ): selector.TimeSelector(),
                vol.Required(
                    "portions", default=current_schedule.get("portions", 1)
                ): int,
            }),
            description_placeholders={
                "info": "Update the feeding schedule. Leave days empty to feed every day",
                "schedule_number": str(self.edit_index + 1),
            },
        )

    async def async_step_view_schedules(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """View current feeding schedules.

        Returns:
            FlowResult: Form showing schedules
        """
        # Format schedules for display
        schedule_text = "\n\n".join([
            f"Schedule {i + 1}:\n"
            f"  Time: {s['time']}\n"
            f"  Days: {', '.join(s.get('days', [])) if s.get('days') else 'Every day'}\n"
            f"  Portions: {s['portions']}"
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
                self.feeding_schedules.pop(schedule_index)
            return await self.async_step_manage_schedules()

        # Create options for schedule selection
        schedule_options = [
            {
                "value": str(i),
                "label": f"{s['time']} - {s['portions']} portion(s) - {', '.join(s.get('days', [])) if s.get('days') else 'Every day'}",
            }
            for i, s in enumerate(self.feeding_schedules)
        ]

        return self.async_show_form(
            step_id="delete_schedule",
            data_schema=vol.Schema({
                vol.Required("schedule_to_delete"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=schedule_options, mode="dropdown"
                    )
                ),
            }),
        )

    async def async_step_done(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Finish schedule management.

        Returns:
            FlowResult: Create entry with all schedules
        """

        _LOGGER.debug(
            " *** Updating feeding schedules: %s", self.feeding_schedules
        )

        # await async_options_updated(self.hass, self.config_entry)

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
            data_schema=vol.Schema({
                vol.Optional(
                    "scan_interval",
                    default=current_scan_interval,
                ): int,
            }),
        )


# class PetlibroOptionsFlowHandler(config_entries.OptionsFlow):
#     """Handle options for the Petlibro integration."""

#     def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
#         """Initialize options flow.

#         Args:
#             config_entry: Config entry instance
#         """

#     async def async_step_init(
#         self,
#         user_input: dict[str, Any] | None = None,
#     ) -> FlowResult:
#         """Manage the options.

#         Args:
#             user_input: User provided options

#         Returns:
#             FlowResult: Either form or create entry
#         """
#         if user_input is not None:
#             return self.async_create_entry(
#                 title="",
#                 data=user_input,
#             )


#         # Build options schema with current values
#         current_scan_interval = self.config_entry.options.get(
#             "scan_interval",
#             DEFAULT_SCAN_INTERVAL,
#         )

#         feed_1_time = self.config_entry.options.get(
#             "feed_1_time",
#             None,
#         )
#         feed_1_portions = self.config_entry.options.get(
#             "feed_1_portions",
#             None,
#         )

#         feed_2_time = self.config_entry.options.get(
#             "feed_2_time",
#             None,
#         )
#         feed_2_portions = self.config_entry.options.get(
#             "feed_2_portions",
#             None,
#         )

#         feed_3_time = self.config_entry.options.get(
#             "feed_3_time",
#             None,
#         )
#         feed_3_portions = self.config_entry.options.get(
#             "feed_3_portions",
#             None,
#         )

#         feed_4_time = self.config_entry.options.get(
#             "feed_4_time",
#             None,
#         )
#         feed_4_portions = self.config_entry.options.get(
#             "feed_4_portions",
#             None,
#         )

#         feed_5_time = self.config_entry.options.get(
#             "feed_5_time",
#             None,
#         )
#         feed_5_portions = self.config_entry.options.get(
#             "feed_5_portions",
#             None,
#         )

#         options_schema = vol.Schema({
#             vol.Optional("schedule_entity"): selector.EntitySelector(
#                 selector.EntitySelectorConfig(domain="schedule")
#             ),
#             # vol.Optional(
#             #     "scan_interval",
#             #     default=current_scan_interval,
#             # ): int,
#             # vol.Required(
#             #     "feed_1_time",
#             #     default=feed_1_time,
#             # ): int,
#             # vol.Required(
#             #     "feed_1_portions",
#             #     default=feed_1_portions,
#             # ): int,
#             # vol.Optional(
#             #     "feed_2_time",
#             #     default=feed_2_time,
#             # ): int,
#             # vol.Optional(
#             #     "feed_2_portions",
#             #     default=feed_2_portions,
#             # ): int,
#             # vol.Optional(
#             #     "feed_3_time",
#             #     default=feed_3_time,
#             # ): int,
#             # vol.Optional(
#             #     "feed_3_portions",
#             #     default=feed_3_portions,
#             # ): int,
#             # vol.Optional(
#             #     "feed_4_time",
#             #     default=feed_4_time,
#             # ): int,
#             # vol.Optional(
#             #     "feed_4_portions",
#             #     default=feed_4_portions,
#             # ): int,
#             # vol.Optional(
#             #     "feed_5_time",
#             #     default=feed_5_time,
#             # ): int,
#             # vol.Optional(
#             #     "feed_5_portions",
#             #     default=feed_5_portions,
#             # ): int,
#         })

#         return self.async_show_form(
#             step_id="init",
#             data_schema=options_schema,
#         )
