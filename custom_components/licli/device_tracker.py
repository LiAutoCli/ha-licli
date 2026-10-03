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

from .const import (
    ATTR_VIN,
    COORDINATOR,
    DOMAIN,
    TRACKER_SLUG,
    entity_id_for,
    unique_id_for,
)
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
    entities: list[TrackerEntity] = []
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

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self._vin = vin
        self.entity_id = entity_id_for("device_tracker", vin, TRACKER_SLUG)
        self._attr_unique_id = unique_id_for(vin, TRACKER_SLUG)
        self._attr_translation_key = TRACKER_SLUG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vin)},
            "name": nickname,
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
