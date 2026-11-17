"""Support for the LiAuto trunk switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_VIN,
    COORDINATOR,
    DOMAIN,
    TRUNK_SLUG,
    entity_id_for,
    unique_id_for,
)
from .coordinator import LicliDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the LiAuto trunk switch."""
    coordinator: LicliDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR
    ]
    entities: list[SwitchEntity] = []
    for vin, data in coordinator.data.items():
        vehicle = data.get("vehicle", {})
        nickname = vehicle.get("vehicleInfo", {}).get("vehicleNickname", vin)
        entities.append(LicliTrunkSwitch(coordinator, vin, nickname))
    async_add_entities(entities)


class LicliTrunkSwitch(
    CoordinatorEntity[LicliDataUpdateCoordinator], SwitchEntity
):
    """Trunk switch: on = open, off = closed.

    State comes from ``status.doors.trunk.open``; turning the switch on sends
    ``trunk open``, turning it off sends ``trunk close``.
    """

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._vin = vin
        self.entity_id = entity_id_for("switch", vin, TRUNK_SLUG)
        self._attr_unique_id = unique_id_for(vin, TRUNK_SLUG)
        self._attr_translation_key = TRUNK_SLUG
        self._attr_has_entity_name = True
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vin)},
            "name": nickname,
            "manufacturer": "Li Auto",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if the trunk is open."""
        status = self.coordinator.data.get(self._vin, {}).get("status", {})
        door = (status.get("doors") or {}).get("trunk") or {}
        return door.get("open")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Open the trunk."""
        await self.coordinator.client.control(self._vin, "trunk", open=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Close the trunk."""
        await self.coordinator.client.control(self._vin, "trunk", open=False)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {ATTR_VIN: self._vin}
