"""Support for LiAuto CLI parking images.

Two image entities per vehicle, sourced from `licli photos <vin> --json`
(requires liauto>=0.1.2b0):

  * ``parking_top``      -> the single top view (``picInTop``, 515x720)
  * ``parking_surround`` -> the four single-camera views (front/rear/left/
    right, 1380x720 each) merged into one 2x2 image with Pillow.

Images refresh on the coordinator cadence (10 min). Locking the car schedules
one extra pull 60s later, so the garaged shots are captured after the car has
settled.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from io import BytesIO
from typing import Any

from homeassistant.components.image import (
    Image,
    ImageEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_PIC_TIME,
    ATTR_VIN,
    COORDINATOR,
    DOMAIN,
    IMAGE_CONTENT_TYPE,
    IMAGE_SPECS,
    PHOTO_QUAD,
    PHOTO_TOP,
    entity_id_for,
    unique_id_for,
)
from .coordinator import LicliDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _merge_2x2(images: list[bytes]) -> bytes:
    """Merge the four camera views into a 2x2 grid (blocking; run in executor)."""
    from PIL import Image as PILImage

    opened = [PILImage.open(BytesIO(b)).convert("RGB") for b in images]
    cw = max(im.width for im in opened)
    ch = max(im.height for im in opened)
    canvas = PILImage.new("RGB", (cw * 2, ch * 2))
    for idx, im in enumerate(opened):
        canvas.paste(im, ((idx % 2) * cw, (idx // 2) * ch))
    buf = BytesIO()
    canvas.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


class LicliParkingImage(CoordinatorEntity[LicliDataUpdateCoordinator], ImageEntity):
    """A parking image entity backed by the LiAuto photo service."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: LicliDataUpdateCoordinator,
        vin: str,
        nickname: str,
        spec: dict[str, Any],
    ) -> None:
        """Initialize the parking image entity."""
        # ImageEntity first (defines async_image/cached_property), then the
        # coordinator wiring.
        ImageEntity.__init__(self, hass)
        CoordinatorEntity.__init__(self, coordinator)
        self._vin = vin
        self._nickname = nickname
        self._kind = spec["kind"]
        self._slug = spec["slug"]

        self.entity_id = entity_id_for("image", vin, self._slug)
        self._attr_unique_id = unique_id_for(vin, self._slug)
        self._attr_translation_key = self._slug
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vin)},
            "name": nickname,
            "manufacturer": "Li Auto",
        }

    # -- data access -------------------------------------------------------

    def _photo(self) -> dict[str, Any]:
        """Return this vehicle's latest photo payload."""
        return self.coordinator.data.get(self._vin, {}).get("photos") or {}

    @staticmethod
    def _by_name(photos: list[dict[str, Any]], name: str) -> str | None:
        """Return the URL for a given photo name, if present."""
        for photo in photos:
            if photo.get("name") == name:
                return photo.get("url")
        return None

    async def _fetch_bytes(self, url: str) -> bytes | None:
        """Fetch raw image bytes (reuses ImageEntity's http client)."""
        response = await self._fetch_url(url)
        if response is None:
            return None
        return response.content

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh the image when the underlying photo capture time changes."""
        new_time = self._pic_time()
        if new_time != self._attr_image_last_updated:
            self._attr_image_last_updated = new_time
            self._cached_image = None
        self.async_write_ha_state()

    def _pic_time(self) -> datetime | None:
        """Parse the photo timestamp into a tz-aware datetime."""
        raw = self._photo().get("timestamp")
        if isinstance(raw, (int, float)):
            return dt_util.as_utc(dt_util.utc_from_timestamp(raw / 1000))
        return None

    # -- ImageEntity API ---------------------------------------------------

    async def async_image(self) -> bytes | None:
        """Return the bytes of the (merged) image."""
        if self._cached_image:
            return self._cached_image.content

        payload = self._photo()
        photos = payload.get("photos") or []

        if self._kind == "top":
            url = self._by_name(photos, PHOTO_TOP)
            content = await self._fetch_bytes(url) if url else None
        else:
            urls = [self._by_name(photos, name) for name in PHOTO_QUAD]
            if any(u is None for u in urls):
                content = None
            else:
                parts = await asyncio.gather(*(self._fetch_bytes(u) for u in urls))
                if any(p is None for p in parts):
                    content = None
                else:
                    content = await self.hass.async_add_executor_job(
                        _merge_2x2, list(parts)
                    )

        if content is None:
            return None

        self._cached_image = Image(content=content, content_type=IMAGE_CONTENT_TYPE)
        self._attr_content_type = IMAGE_CONTENT_TYPE
        return content

    @property
    def image_last_updated(self) -> datetime | None:
        """When the image was last refreshed (the photo capture time)."""
        if self._attr_image_last_updated is None:
            self._attr_image_last_updated = self._pic_time()
        return self._attr_image_last_updated

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes (raw picTime alongside the parsed state)."""
        return {
            ATTR_VIN: self._vin,
            ATTR_PIC_TIME: self._photo().get(ATTR_PIC_TIME),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LiAuto parking images."""
    coordinator: LicliDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR
    ]
    entities: list[ImageEntity] = []
    for vin, data in coordinator.data.items():
        vehicle = data.get("vehicle", {})
        nickname = vehicle.get("vehicleInfo", {}).get("vehicleNickname", vin)
        for spec in IMAGE_SPECS:
            entities.append(LicliParkingImage(hass, coordinator, vin, nickname, spec))
    async_add_entities(entities)
