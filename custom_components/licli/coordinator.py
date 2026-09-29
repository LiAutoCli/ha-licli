"""DataUpdateCoordinator for LiAuto CLI."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from .client import LicliClient, LicliError

_LOGGER = logging.getLogger(__name__)


class LicliDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Coordinator to fetch data for all vehicles."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: LicliClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        self.client = client
        interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> dict[str, dict]:
        """Fetch data for all vehicles."""
        try:
            vehicles = await self.client.vehicles()
        except LicliError as err:
            raise UpdateFailed(f"Failed to list vehicles: {err}") from err

        data: dict[str, dict] = {}
        for v in vehicles:
            vin = v["vin"]
            try:
                status = await self.client.status(vin)
                location = await self.client.location(vin)
                data[vin] = {
                    "vehicle": v,
                    "status": status,
                    "location": location,
                }
            except LicliError as err:
                _LOGGER.warning("Failed to fetch status for %s: %s", vin, err)
                data[vin] = {
                    "vehicle": v,
                    "status": {},
                    "location": None,
                }

        return data
