"""Support for LiAuto CLI sensors."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_VIN,
    COORDINATOR,
    DOMAIN,
    SENSOR_SPECS,
    TIRE_SPECS,
    entity_id_for,
    unique_id_for,
)
from .coordinator import LicliDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_DEVICE_CLASSES = {
    "battery": SensorDeviceClass.BATTERY,
    "distance": SensorDeviceClass.DISTANCE,
    "temperature": SensorDeviceClass.TEMPERATURE,
    "enum": SensorDeviceClass.ENUM,
}

_UNITS = {
    "%": PERCENTAGE,
    "km": UnitOfLength.KILOMETERS,
    "°C": UnitOfTemperature.CELSIUS,
}

_STATE_CLASSES = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}


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
        for spec in SENSOR_SPECS:
            entities.append(LicliSensor(coordinator, vin, nickname, spec))
        for spec in TIRE_SPECS:
            entities.append(LicliTireSensor(coordinator, vin, nickname, spec))
    async_add_entities(entities)


class LicliSensor(CoordinatorEntity[LicliDataUpdateCoordinator], SensorEntity):
    """Representation of a LiAuto sensor."""

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
        self._nickname = nickname
        self._field = spec.get("field")
        self._compute = spec.get("compute")
        self._slug = spec["slug"]
        self._is_enum = spec.get("device_class") == "enum"

        # Explicit entity_id (mechanism B): <platform>.{vin_sort}_{slug}
        self.entity_id = entity_id_for("sensor", vin, self._slug)
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
        if spec.get("unit"):
            self._attr_native_unit_of_measurement = _UNITS[spec["unit"]]
        if spec.get("state_class"):
            self._attr_state_class = _STATE_CLASSES[spec["state_class"]]
        if spec.get("options"):
            self._attr_options = spec["options"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {ATTR_VIN: self._vin}


class LicliTireSensor(CoordinatorEntity[LicliDataUpdateCoordinator], SensorEntity):
    """Tyre-pressure sensor (option B).

    State = pressure (kPa). Tyre temperature and warning flags are exposed as
    extra attributes, keeping the entity count low.
    """

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
        spec: dict[str, Any],
    ) -> None:
        """Initialize the tyre sensor."""
        super().__init__(coordinator)
        self._vin = vin
        self._pos = spec["pos"]
        self._slug = spec["slug"]
        self.entity_id = entity_id_for("sensor", vin, self._slug)
        self._attr_unique_id = unique_id_for(vin, self._slug)
        self._attr_translation_key = self._slug
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vin)},
            "name": nickname,
            "manufacturer": "Li Auto",
        }
        self._attr_device_class = SensorDeviceClass.PRESSURE
        self._attr_native_unit_of_measurement = UnitOfPressure.KPA
        self._attr_state_class = SensorStateClass.MEASUREMENT

    def _tire(self) -> dict[str, Any]:
        """Return this wheel's raw dict."""
        tires = self.coordinator.data.get(self._vin, {}).get("tire") or {}
        return tires.get(self._pos) or {}

    @property
    def native_value(self) -> Any:
        """Return the tyre pressure."""
        return self._tire().get("pressure")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Tyre temperature + warning flags ride along as attributes."""
        t = self._tire()
        return {
            ATTR_VIN: self._vin,
            "temperature": t.get("temp"),
            "pressure_warning": t.get("pressureWarning"),
            "temperature_warning": t.get("tempWarning"),
        }
