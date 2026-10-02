"""Support for LiAuto CLI device trackers."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import (
    SourceType,
    TrackerEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, COORDINATOR, ATTR_VIN
from .coordinator import LicliDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LiAuto device trackers."""
    coordinator: LicliDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR
    ]
    entities = []
    for vin, data in coordinator.data.items():
        vehicle = data.get("vehicle", {})
        nickname = vehicle.get("vehicleInfo", {}).get("vehicleNickname", vin)
        entities.append(LicliDeviceTracker(coordinator, vin, nickname))
    async_add_entities(entities)


class LicliDeviceTracker(
    CoordinatorEntity[LicliDataUpdateCoordinator], TrackerEntity
):
    """Representation of a LiAuto vehicle location."""

    _attr_has_entity_name = True
    _attr_name = "位置"

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self._vin = vin
        self._nickname = nickname
        self._attr_unique_id = f"{DOMAIN}_{vin}_location"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info, so the tracker groups under the vehicle device."""
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": self._nickname,
            "manufacturer": "Li Auto",
        }

    @property
    def source_type(self) -> str:
        """Return the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude."""
        loc = self.coordinator.data.get(self._vin, {}).get("location")
        if loc and loc.get("valid"):
            return loc["lat"]
        return None

    @property
    def longitude(self) -> float | None:
        """Return longitude."""
        loc = self.coordinator.data.get(self._vin, {}).get("location")
        if loc and loc.get("valid"):
            return loc["lon"]
        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        loc = self.coordinator.data.get(self._vin, {}).get("location") or {}
        attrs = {ATTR_VIN: self._vin}
        if loc:
            if "dir" in loc:
                attrs["direction"] = loc["dir"]
            if "alt" in loc:
                attrs["altitude"] = loc["alt"]
            if "spd" in loc:
                attrs["speed"] = loc["spd"]
            if "timestamp" in loc:
                attrs["location_timestamp"] = loc["timestamp"]
        return attrs
