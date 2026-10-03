"""Support for LiAuto CLI binary sensors."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_VIN,
    COORDINATOR,
    DOMAIN,
    DOOR_SPECS,
    ONLINE_SPECS,
    entity_id_for,
    unique_id_for,
)
from .coordinator import LicliDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_DEVICE_CLASSES = {
    "connectivity": BinarySensorDeviceClass.CONNECTIVITY,
    "door": BinarySensorDeviceClass.DOOR,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LiAuto binary sensors."""
    coordinator: LicliDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR
    ]
    entities: list[BinarySensorEntity] = []
    for vin, data in coordinator.data.items():
        vehicle = data.get("vehicle", {})
        nickname = vehicle.get("vehicleInfo", {}).get("vehicleNickname", vin)
        for spec in ONLINE_SPECS:
            entities.append(LicliBinarySensor(coordinator, vin, nickname, spec))
        for spec in DOOR_SPECS:
            entities.append(LicliDoorSensor(coordinator, vin, nickname, spec))
    async_add_entities(entities)


class LicliBinarySensor(
    CoordinatorEntity[LicliDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of a LiAuto binary sensor."""

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
        spec: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._vin = vin
        self._field = spec["field"]
        self._slug = spec["slug"]
        self.entity_id = entity_id_for("binary_sensor", vin, self._slug)
        self._attr_unique_id = unique_id_for(vin, self._slug)
        self._attr_translation_key = self._slug
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vin)},
            "name": nickname,
            "manufacturer": "Li Auto",
        }
        if spec.get("device_class"):
            self._attr_device_class = _DEVICE_CLASSES[spec["device_class"]]

    @property
    def is_on(self) -> bool | None:
        """Return true if the sensor is on."""
        status = self.coordinator.data.get(self._vin, {}).get("status", {})
        value = status.get(self._field)
        if value is None:
            return None
        return bool(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {ATTR_VIN: self._vin}


class LicliDoorSensor(
    CoordinatorEntity[LicliDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of a LiAuto door open sensor."""

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
        spec: dict[str, Any],
    ) -> None:
        """Initialize the door sensor."""
        super().__init__(coordinator)
        self._vin = vin
        self._door = spec["door"]
        self._slug = spec["slug"]
        self.entity_id = entity_id_for("binary_sensor", vin, self._slug)
        self._attr_unique_id = unique_id_for(vin, self._slug)
        self._attr_translation_key = self._slug
        self._attr_has_entity_name = True
        self._attr_device_class = BinarySensorDeviceClass.DOOR
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vin)},
            "name": nickname,
            "manufacturer": "Li Auto",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if door is open."""
        status = self.coordinator.data.get(self._vin, {}).get("status", {})
        door = (status.get("doors") or {}).get(self._door) or {}
        return door.get("open")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {ATTR_VIN: self._vin}
