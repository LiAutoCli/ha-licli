"""Support for LiAuto CLI buttons."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
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
    """Set up LiAuto buttons."""
    coordinator: LicliDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR
    ]
    entities = []
    for vin, data in coordinator.data.items():
        vehicle = data.get("vehicle", {})
        nickname = vehicle.get("vehicleInfo", {}).get("vehicleNickname", vin)
        entities.append(LicliButton(coordinator, vin, nickname, "find", "寻车"))
        entities.append(LicliButton(coordinator, vin, nickname, "wake", "唤醒"))
        entities.append(LicliButton(coordinator, vin, nickname, "trunk", "尾门开关", open_trunk=True))
    async_add_entities(entities)


class LicliButton(CoordinatorEntity[LicliDataUpdateCoordinator], ButtonEntity):
    """Representation of a LiAuto button."""

    def __init__(
        self,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
        action: str,
        label: str,
        open_trunk: bool = False,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._vin = vin
        self._action = action
        self._open_trunk = open_trunk
        self._attr_unique_id = f"{DOMAIN}_{vin}_{action}{'_trunk_open' if open_trunk else ''}"
        self._attr_name = f"{nickname} {label}"
        self._attr_has_entity_name = True

    async def async_press(self) -> None:
        """Handle button press."""
        kwargs: dict[str, Any] = {}
        if self._action == "trunk":
            kwargs["open"] = self._open_trunk
        await self.coordinator.client.control(self._vin, self._action, **kwargs)
