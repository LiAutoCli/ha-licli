"""Config flow for LiAuto CLI integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_MODE,
    CONF_HOST,
    CONF_TOKEN,
    CONF_ACTIVATION_CODE,
    MODE_HTTP,
    MODE_LOCAL,
    DEFAULT_HTTP_PORT,
)
from .client import LicliClient

_LOGGER = logging.getLogger(__name__)

MODE_OPTIONS = [
    (MODE_HTTP, "HTTP (licli serve)"),
    (MODE_LOCAL, "Local CLI (uvx liauto / licli)"),
]


class LicliConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LiAuto CLI."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mode = user_input[CONF_MODE]
            if mode == MODE_HTTP:
                host = user_input.get(CONF_HOST, f"http://127.0.0.1:{DEFAULT_HTTP_PORT}")
                token = user_input.get(CONF_TOKEN, "")
                # Validate connection
                try:
                    client = LicliClient(
                        self.hass,
                        {CONF_MODE: mode, CONF_HOST: host, CONF_TOKEN: token},
                    )
                    vehicles = await client.vehicles()
                    if not vehicles:
                        errors["base"] = "no_vehicles"
                    else:
                        return self.async_create_entry(
                            title=f"LiAuto CLI ({host})",
                            data={
                                CONF_MODE: mode,
                                CONF_HOST: host,
                                CONF_TOKEN: token,
                            },
                        )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("HTTP mode validation failed: %s", err)
                    errors["base"] = "cannot_connect"
            else:
                code = user_input.get(CONF_ACTIVATION_CODE, "")
                return self.async_create_entry(
                    title="LiAuto CLI (local)",
                    data={
                        CONF_MODE: mode,
                        CONF_ACTIVATION_CODE: code,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODE, default=MODE_HTTP): vol.In(
                        dict(MODE_OPTIONS)
                    ),
                    vol.Optional(
                        CONF_HOST,
                        default=f"http://127.0.0.1:{DEFAULT_HTTP_PORT}",
                    ): str,
                    vol.Optional(CONF_TOKEN, default=""): str,
                    vol.Optional(CONF_ACTIVATION_CODE, default=""): str,
                }
            ),
            errors=errors,
        )
