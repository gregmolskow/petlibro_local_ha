"""petlibro_mqtt_ha.

This module initializes the Petlibro MQTT Home Assistant
integration that connects to Petlibro devices via MQTT.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN as DOMAIN  # DOMAIN = "your_integration_name"
from .coordinator import PetlibroCoordinator
from .ha_plaf301 import PLAF301
from .vacuum import PLAF301Entity

PLATFORMS: list[str] = ["vacuum"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Petlibro integration from ConfigEntry.

    Parameters
    ----------
    hass : HomeAssistant
        _description_
    entry : ConfigEntry
        _description_

    Returns
    -------
    bool
        _description_

    """
    config = entry.data
    sn: str = config.get("petlibro_serial_number")
    name: str = config.get("petlibro_device_name")
    feeder = PLAF301(hass, sn, name)
    coordinator = PetlibroCoordinator(hass, entry, feeder)
    entity = PLAF301Entity(hass, name, sn, coordinator)
    coordinator.entity = entity
    entry.runtime_data = coordinator
    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["vacuum"])
    coordinator.entity = entity
    await coordinator.async_config_entry_first_refresh()

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


# async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#     """Unload a config entry."""
#     unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
#     if unload_ok:
#         hass.data[DOMAIN].pop(entry.entry_id)
#     return unload_ok
