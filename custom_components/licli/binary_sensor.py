"""Support for LiAuto CLI binary sensors."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
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
    """Set up LiAuto binary sensors."""
    coordinator: LicliDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR
    ]
    entities = []
    for vin, data in coordinator.data.items():
        vehicle = data.get("vehicle", {})
        nickname = vehicle.get("vehicleInfo", {}).get("vehicleNickname", vin)
        entities.append(
            LicliBinarySensor(
                coordinator, vin, nickname, "online", "在线",
                device_class=BinarySensorDeviceClass.CONNECTIVITY
            )
        )
        entities.append(
            LicliBinarySensor(
                coordinator, vin, nickname, "chargingStatus", "充电中",
                is_charging=True,
                device_class=BinarySensorDeviceClass.BATTERY_CHARGING
            )
        )
        # Per-door open sensors
        for door in ["driver", "passenger", "rearLeft", "rearRight", "trunk"]:
            entities.append(
                LicliDoorSensor(coordinator, vin, nickname, door)
            )
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
        field: str,
        label: str,
        is_charging: bool = False,
        device_class: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._vin = vin
        self._field = field
        self._is_charging = is_charging
        self._attr_unique_id = f"{DOMAIN}_{vin}_{field}"
        self._attr_name = f"{nickname} {label}"
        self._attr_has_entity_name = True
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool | None:
        """Return true if the sensor is on."""
        status = self.coordinator.data.get(self._vin, {}).get("status", {})
        value = status.get(self._field)
        if self._is_charging:
            return value == "charging"
        if self._field == "online":
            return bool(value)
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
        door: str,
    ) -> None:
        """Initialize the door sensor."""
        super().__init__(coordinator)
        self._vin = vin
        self._door = door
        door_labels = {
            "driver": "主驾门",
            "passenger": "副驾门",
            "rearLeft": "左后门",
            "rearRight": "右后门",
            "trunk": "尾门",
        }
        self._attr_unique_id = f"{DOMAIN}_{vin}_door_{door}_open"
        self._attr_name = f"{nickname} {door_labels.get(door, door)}"
        self._attr_has_entity_name = True
        self._attr_device_class = BinarySensorDeviceClass.DOOR

    @property
    def is_on(self) -> bool | None:
        """Return true if door is open."""
        status = self.coordinator.data.get(self._vin, {}).get("status", {})
        doors = status.get("doors", {})
        door = doors.get(self._door, {})
        return door.get("open")
