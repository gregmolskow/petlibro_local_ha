from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .ha_plaf301 import PLAF301
import logging

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=5)


class PetlibroCoordinator(DataUpdateCoordinator[None]):
    """Coordinator to manage Petlibro vacuum data."""

    feeder: PLAF301 | None = None
    entity = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        feeder: PLAF301,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=config_entry,
            update_interval=UPDATE_INTERVAL,
            name=DOMAIN,
        )
        self.feeder = feeder

    async def _async_update_data(self) -> dict:
        """Fetch data from vacuum backend."""
        try:
            # This should return a dict of state values
            await self.feeder.update_state()
            # await self.entity.async_write_ha_state()
            return self.feeder.status
        except Exception as err:
            msg = f"Could not update Petlibro vacuum: {err}"
            raise UpdateFailed(msg)  # noqa: B904
