"""Configuration flow for the Petlibro MQTT Home Assistant integration.

This module defines the setup and options flow for configuring the integration
via the Home Assistant UI, including user input validation and entry creation.
"""

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN  # DOMAIN = "your_integration_name"

# Schema for the user-facing setup form
data_schema = vol.Schema(
    {
        vol.Required("petlibro_serial_number"): cv.string,
        vol.Optional("petlibro_device_name"): cv.string,
    },
)

option_schema = vol.Schema(
    {
        vol.Optional("scan_interval", default=60): int,
    },
)


class PetlibroMqttHaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Manage the configuration flow for the Petlibro MQTT HA integration.

    This class handles user interaction when setting up the integration
    through the Home Assistant UI. It defines the steps required for the
    user to configure the integration and creates a config entry.

    :cvar VERSION: The version of the config entry schema.
    :cvar CONNECTION_CLASS: The type of connection (polling, cloud, etc.).
    """

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> FlowResult:
        """Handle the initial step of the config flow.

        This method is triggered when the user first adds the integration via the UI.
        It displays a form asking for the required connection parameters.

        :param user_input: Optional dictionary of user-submitted input.
        :type user_input: dict | None

        :return: The result of the flow step. This may be a form or a config entry.
        :rtype: FlowResult
        """
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input['petlibro_serial_number']}",
            )
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="Petlibro MQTT HA",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler for this integration.

        This method is called when the user clicks "Configure" on an
        existing config entry in the UI.

        :param config_entry: The existing config entry.
        :type config_entry: ConfigEntry

        :return: Options flow handler instance.
        :rtype: OptionsFlow
        """
        return PetlibroMQTTHAOptionsFlowHandler(config_entry)


class PetlibroMQTTHAOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for the integration after initial setup.

    This class defines the flow for modifying configuration options
    of an already-installed integration entry. It allows users to
    change parameters such as scan intervals or polling behavior.

    :param config_entry: The existing config entry.
    :type config_entry: ConfigEntry
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow handler.

        :param config_entry: The config entry for which this options flow is being executed.
        :type config_entry: ConfigEntry
        """
        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict | None = None,
    ) -> FlowResult:
        """Manage the initial step in the options flow.

        This is the entry point when the user selects "Configure" on the integration.

        :param user_input: Optional dictionary of option values submitted by the user.
        :type user_input: dict | None

        :return: A result object indicating either form display or entry creation.
        :rtype: FlowResult
        """
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=option_schema,
        )
