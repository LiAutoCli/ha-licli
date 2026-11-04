"""DataUpdateCoordinator for LiAuto CLI."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_PROFILE,
    CONF_DRIVE_FREQUENT,
    DEFAULT_SCAN_PROFILE,
    DEFAULT_DRIVE_FREQUENT,
    DRIVE_INTERVAL,
    MOVING_GEARS,
    scan_interval_seconds,
)
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
        # Base poll interval from the scan "profile" (a multiplier of the base
        # interval); fall back to a legacy raw-seconds option if present.
        profile = entry.options.get(CONF_SCAN_PROFILE)
        if profile:
            base_interval = scan_interval_seconds(profile)
        else:
            base_interval = entry.options.get(
                CONF_SCAN_INTERVAL, scan_interval_seconds(DEFAULT_SCAN_PROFILE)
            )
        self._base_interval = int(base_interval)
        self._current_interval = self._base_interval
        # Optional: poll faster (DRIVE_INTERVAL) while a vehicle is not in P.
        self._drive_frequent = bool(
            entry.options.get(CONF_DRIVE_FREQUENT, DEFAULT_DRIVE_FREQUENT)
        )
        _LOGGER.debug(
            "LiAuto poll interval: %ss base (profile=%s, drive_frequent=%s)",
            self._base_interval,
            profile or "default",
            self._drive_frequent,
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self._base_interval),
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
                try:
                    tire = await self.client.tire(vin)
                except LicliError as err:
                    _LOGGER.warning("Failed to fetch tire for %s: %s", vin, err)
                    tire = {}
                data[vin] = {
                    "vehicle": v,
                    "status": status,
                    "location": location,
                    "tire": tire,
                }
            except LicliError as err:
                _LOGGER.warning("Failed to fetch status for %s: %s", vin, err)
                data[vin] = {
                    "vehicle": v,
                    "status": {},
                    "location": None,
                    "tire": {},
                }

        self._async_apply_drive_interval(data)
        return data

    @callback
    def _async_apply_drive_interval(self, data: dict[str, dict]) -> None:
        """Poll every ``DRIVE_INTERVAL`` seconds while any vehicle is not in P.

        When the option is off, or every car is parked (P/unknown), fall back
        to the configured base interval. Setting ``update_interval`` here takes
        effect on the next scheduled refresh: the coordinator re-schedules at
        the end of every refresh cycle.
        """
        desired = self._base_interval
        if self._drive_frequent:
            driving = any(
                isinstance(d.get("status"), dict)
                and d["status"].get("gear") in MOVING_GEARS
                for d in data.values()
            )
            if driving:
                desired = DRIVE_INTERVAL
        if desired != self._current_interval:
            self._current_interval = desired
            self.update_interval = timedelta(seconds=desired)
            _LOGGER.info(
                "LiAuto poll interval changed to %ss (drive_frequent=%s)",
                desired,
                self._drive_frequent,
            )
