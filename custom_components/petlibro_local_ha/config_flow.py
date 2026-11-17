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

from .shared_const import (
    _LOGGER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

# Serial number validation pattern (alphanumeric, typically 12+ characters)
SERIAL_NUMBER_PATTERN = re.compile(r"^[A-Z0-9]{10,}$", re.IGNORECASE)

DEVICE_TYPES = [
    {"value": "auto", "label": "Auto-detect from serial number"},
    {"value": "feeder", "label": "Feeder (PLAF301)"},
    {"value": "fountain", "label": "Water Fountain (PLWF116)"},
]


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

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure other settings like scan interval.

        Args:
            user_input: User provided settings

        Returns:
            FlowResult: Form or create entry
        """
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
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
            step_id="init",
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
