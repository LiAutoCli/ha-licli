"""Support for LiAuto CLI locks."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityFeature
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
    """Set up LiAuto locks."""
    coordinator: LicliDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR
    ]
    entities = []
    for vin, data in coordinator.data.items():
        vehicle = data.get("vehicle", {})
        nickname = vehicle.get("vehicleInfo", {}).get("vehicleNickname", vin)
        entities.append(LicliLock(coordinator, vin, nickname))
    async_add_entities(entities)


class LicliLock(CoordinatorEntity[LicliDataUpdateCoordinator], LockEntity):
    """Representation of a LiAuto vehicle lock."""

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
    ) -> None:
        """Initialize the lock."""
        super().__init__(coordinator)
        self._vin = vin
        self._attr_unique_id = f"{DOMAIN}_{vin}_lock"
        self._attr_name = f"{nickname} 门锁"
        self._attr_has_entity_name = True
        self._attr_supported_features = LockEntityFeature.OPEN

    @property
    def is_locked(self) -> bool | None:
        """Return true if vehicle is locked."""
        status = self.coordinator.data.get(self._vin, {}).get("status", {})
        doors = status.get("doors", {})
        driver = doors.get("driver", {})
        if not driver:
            return None
        return bool(driver.get("locked"))

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the vehicle."""
        await self.coordinator.client.control(self._vin, "lock")
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the vehicle."""
        await self.coordinator.client.control(self._vin, "unlock")
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        attrs: dict[str, Any] = {ATTR_VIN: self._vin}
        status = self.coordinator.data.get(self._vin, {}).get("status", {})
        doors = status.get("doors", {})
        for door, state in doors.items():
            attrs[f"door_{door}_open"] = state.get("open")
            attrs[f"door_{door}_locked"] = state.get("locked")
        return attrs