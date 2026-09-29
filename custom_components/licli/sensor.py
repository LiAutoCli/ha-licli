"""Support for LiAuto CLI sensors."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfEnergy
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
    """Set up LiAuto sensors."""
    coordinator: LicliDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR
    ]
    entities: list[SensorEntity] = []
    for vin, data in coordinator.data.items():
        vehicle = data.get("vehicle", {})
        nickname = vehicle.get("vehicleInfo", {}).get("vehicleNickname", vin)
        entities.append(LicliSensor(coordinator, vin, nickname, "batteryLevel", "电量", PERCENTAGE, SensorDeviceClass.BATTERY))
        entities.append(LicliSensor(coordinator, vin, nickname, "electricRange", "纯电续航", UnitOfLength.KILOMETERS))
        entities.append(LicliSensor(coordinator, vin, nickname, "fuelRange", "燃油续航", UnitOfLength.KILOMETERS))
        entities.append(LicliSensor(coordinator, vin, nickname, "totalMileage", "总里程", UnitOfLength.KILOMETERS))
        entities.append(LicliSensor(coordinator, vin, nickname, "adMileage", "AD里程", UnitOfLength.KILOMETERS))
        entities.append(LicliSensor(coordinator, vin, nickname, "acTemp", "空调温度", None, SensorDeviceClass.TEMPERATURE))
    async_add_entities(entities)


class LicliSensor(CoordinatorEntity[LicliDataUpdateCoordinator], SensorEntity):
    """Representation of a LiAuto sensor."""

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
        field: str,
        label: str,
        unit: str | None,
        device_class: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._vin = vin
        self._field = field
        self._attr_unique_id = f"{DOMAIN}_{vin}_{field}"
        self._attr_name = f"{nickname} {label}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": self._attr_name.rsplit(" ", 1)[0],
            "manufacturer": "Li Auto",
        }

    @property
    def native_value(self) -> Any:
        """Return the state."""
        data = self.coordinator.data.get(self._vin, {})
        status = data.get("status", {})
        return status.get(self._field)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {ATTR_VIN: self._vin}
