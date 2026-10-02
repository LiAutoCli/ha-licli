"""Support for LiAuto CLI climate (AC)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
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
    """Set up LiAuto climate."""
    coordinator: LicliDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR
    ]
    entities = []
    for vin, data in coordinator.data.items():
        vehicle = data.get("vehicle", {})
        nickname = vehicle.get("vehicleInfo", {}).get("vehicleNickname", vin)
        entities.append(LicliClimate(coordinator, vin, nickname))
    async_add_entities(entities)


class LicliClimate(CoordinatorEntity[LicliDataUpdateCoordinator], ClimateEntity):
    """Representation of a LiAuto vehicle climate."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 16.0
    _attr_max_temp = 32.0
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._vin = vin
        self._nickname = nickname
        self._attr_unique_id = f"{DOMAIN}_{vin}_climate"
        self._attr_name = f"{nickname} 空调"
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info, so the entity groups under the vehicle device."""
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": self._nickname,
            "manufacturer": "Li Auto",
        }

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current HVAC mode."""
        status = self.coordinator.data.get(self._vin, {}).get("status", {})
        ac = status.get("acStatus", "off")
        return HVACMode.HEAT_COOL if ac != "off" else HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        status = self.coordinator.data.get(self._vin, {}).get("status", {})
        return status.get("acTemp")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.client.control(self._vin, "ac_off")
        else:
            await self.coordinator.client.control(self._vin, "ac_on")
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        temp = kwargs.get("temperature")
        if temp is not None:
            await self.coordinator.client.control(
                self._vin, "ac_temp", temp=temp
            )
        await self.coordinator.async_request_refresh()
