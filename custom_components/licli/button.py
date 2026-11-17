"""Support for LiAuto CLI buttons."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_VIN,
    BUTTON_SPECS,
    COORDINATOR,
    DOMAIN,
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
    """Set up LiAuto buttons."""
    coordinator: LicliDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR
    ]
    entities: list[ButtonEntity] = []
    for vin, data in coordinator.data.items():
        vehicle = data.get("vehicle", {})
        nickname = vehicle.get("vehicleInfo", {}).get("vehicleNickname", vin)
        for spec in BUTTON_SPECS:
            entities.append(LicliButton(coordinator, vin, nickname, spec))
    async_add_entities(entities)


class LicliButton(CoordinatorEntity[LicliDataUpdateCoordinator], ButtonEntity):
    """Representation of a LiAuto button."""

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
        spec: dict[str, Any],
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._vin = vin
        self._action = spec["action"]
        self._slug = spec["slug"]
        self.entity_id = entity_id_for("button", vin, self._slug)
        self._attr_unique_id = unique_id_for(vin, self._slug)
        self._attr_translation_key = self._slug
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vin)},
            "name": nickname,
            "manufacturer": "Li Auto",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {ATTR_VIN: self._vin}

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.client.control(self._vin, self._action)
