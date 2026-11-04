"""DataUpdateCoordinator for LiAuto CLI."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
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
    PHOTOS_SNAPSHOT_DELAYS,
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
        self._photo_snapshot_unsubs: dict[str, list[CALLBACK_TYPE]] = {}
        self._prev_all_locked: dict[str, bool] = {}
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
            entry_data: dict = {
                "vehicle": v,
                "status": {},
                "location": None,
                "tire": {},
                "photos": {},
            }
            try:
                entry_data["status"] = await self.client.status(vin)
                entry_data["location"] = await self.client.location(vin)
            except LicliError as err:
                _LOGGER.warning("Failed to fetch status for %s: %s", vin, err)
            try:
                entry_data["tire"] = await self.client.tire(vin)
            except LicliError as err:
                _LOGGER.warning("Failed to fetch tire for %s: %s", vin, err)
            try:
                entry_data["photos"] = await self.client.photos(vin)
            except LicliError as err:
                _LOGGER.warning("Failed to fetch photos for %s: %s", vin, err)
            data[vin] = entry_data
            self._async_track_lock_state(vin, entry_data["status"])

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

    # -- post-lock photo snapshot -----------------------------------------

    @staticmethod
    def _all_doors_locked(status: dict[str, Any]) -> bool | None:
        """Return True if every door reports locked; None if unknown."""
        doors = status.get("doors") if isinstance(status, dict) else None
        if not doors:
            return None
        return all(bool(d.get("locked")) for d in doors.values())

    @callback
    def _async_track_lock_state(self, vin: str, status: dict[str, Any]) -> None:
        """Schedule photo snapshots when the vehicle becomes all-doors-locked.

        Triggers on the transition into the all-locked state (rather than on the
        HA lock command), so externally-initiated locks are covered too. The
        first observation only seeds the state and never fires.
        """
        now_locked = self._all_doors_locked(status)
        if now_locked is None:  # unknown (e.g. status fetch failed): keep last
            return
        prev = self._prev_all_locked.get(vin)
        self._prev_all_locked[vin] = now_locked
        if prev is False and now_locked:
            self.async_schedule_photo_snapshots(vin)

    @callback
    def async_schedule_photo_snapshots(self, vin: str) -> None:
        """Re-pull this vehicle's photos at each PHOTOS_SNAPSHOT_DELAYS offset.

        Called once the car has become all-doors-locked, so the parking shots
        settle before being captured. Re-scheduling cancels any pending
        snapshots for the same vehicle.
        """
        self._cancel_photo_snapshots(vin)
        for delay in PHOTOS_SNAPSHOT_DELAYS:
            self._photo_snapshot_unsubs.setdefault(vin, []).append(
                async_call_later(self.hass, delay, self._make_snapshot(vin))
            )

    def _make_snapshot(self, vin: str):
        """Build the one-shot callback for a single photo snapshot."""
        async def _snapshot(_now) -> None:
            await self._async_photo_snapshot(vin)

        return _snapshot

    @callback
    def _cancel_photo_snapshots(self, vin: str) -> None:
        """Cancel any pending photo snapshots for one vehicle."""
        for unsub in self._photo_snapshot_unsubs.pop(vin, []):
            unsub()

    async def _async_photo_snapshot(self, vin: str) -> None:
        """Fetch photos for one vehicle and notify listeners."""
        try:
            photos = await self.client.photos(vin)
        except LicliError as err:
            _LOGGER.warning("Post-lock photo snapshot failed for %s: %s", vin, err)
            return
        if vin in self.data:
            self.data[vin]["photos"] = photos
            self.async_update_listeners()

    async def async_shutdown(self) -> None:
        """Cancel pending snapshots and shut the coordinator down."""
        for unsubs in self._photo_snapshot_unsubs.values():
            for unsub in unsubs:
                unsub()
        self._photo_snapshot_unsubs.clear()
        await super().async_shutdown()
