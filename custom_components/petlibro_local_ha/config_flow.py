"""Configuration flow for Petlibro MQTT Home Assistant integration."""

from __future__ import annotations

import re
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

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

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Manage the options.

        Args:
            user_input: User provided options

        Returns:
            FlowResult: Either form or create entry
        """
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=user_input,
            )

        # Build options schema with current values
        current_scan_interval = self.config_entry.options.get(
            "scan_interval",
            DEFAULT_SCAN_INTERVAL,
        )

        feed_1_time = self.config_entry.options.get(
            "feed_1_time",
            None,
        )
        feed_1_portions = self.config_entry.options.get(
            "feed_1_portions",
            None,
        )

        feed_2_time = self.config_entry.options.get(
            "feed_2_time",
            None,
        )
        feed_2_portions = self.config_entry.options.get(
            "feed_2_portions",
            None,
        )

        feed_3_time = self.config_entry.options.get(
            "feed_3_time",
            None,
        )
        feed_3_portions = self.config_entry.options.get(
            "feed_3_portions",
            None,
        )

        feed_4_time = self.config_entry.options.get(
            "feed_4_time",
            None,
        )
        feed_4_portions = self.config_entry.options.get(
            "feed_4_portions",
            None,
        )

        feed_5_time = self.config_entry.options.get(
            "feed_5_time",
            None,
        )
        feed_5_portions = self.config_entry.options.get(
            "feed_5_portions",
            None,
        )

        options_schema = vol.Schema({
            vol.Optional(
                "scan_interval",
                default=current_scan_interval,
            ): int,
            vol.Required(
                "feed_1_time",
                default=feed_1_time,
            ): int,
            vol.Required(
                "feed_1_portions",
                default=feed_1_portions,
            ): int,
            vol.Optional(
                "feed_2_time",
                default=feed_2_time,
            ): int,
            vol.Optional(
                "feed_2_portions",
                default=feed_2_portions,
            ): int,
            vol.Optional(
                "feed_3_time",
                default=feed_3_time,
            ): int,
            vol.Optional(
                "feed_3_portions",
                default=feed_3_portions,
            ): int,
            vol.Optional(
                "feed_4_time",
                default=feed_4_time,
            ): int,
            vol.Optional(
                "feed_4_portions",
                default=feed_4_portions,
            ): int,
            vol.Optional(
                "feed_5_time",
                default=feed_5_time,
            ): int,
            vol.Optional(
                "feed_5_portions",
                default=feed_5_portions,
            ): int,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )
