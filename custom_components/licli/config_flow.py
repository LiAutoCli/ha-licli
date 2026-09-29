"""Config flow for LiAuto CLI integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
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
from .client import LicliClient, LicliLoginSession, async_activate, LicliError

_LOGGER = logging.getLogger(__name__)

STEP_MODE = "mode"
STEP_HTTP = "http"
STEP_LOCAL_REUSE = "local_reuse"
STEP_LOCAL_AUTH = "local_auth"
STEP_LOCAL_ACTIVATE = "local_activate"
STEP_LOCAL_TOKEN = "local_token"


class LicliConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LiAuto CLI."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._mode: str | None = None
        self._host: str = f"http://127.0.0.1:{DEFAULT_HTTP_PORT}"
        self._token: str = ""
        self._code: str = ""
        self._login_session: LicliLoginSession | None = None

    async def async_step_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose connection mode."""
        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            if self._mode == MODE_HTTP:
                return await self.async_step_http()
            return await self.async_step_local_reuse()

        return self.async_show_menu(
            step_id=STEP_MODE,
            menu_options=[MODE_HTTP, MODE_LOCAL],
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Local CLI entry: reuse or re-authorize."""
        return await self.async_step_local_reuse(user_input)

    async def async_step_http(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure HTTP mode."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input.get(CONF_HOST, self._host)
            self._token = user_input.get(CONF_TOKEN, "")
            try:
                client = LicliClient(
                    self.hass,
                    {CONF_MODE: MODE_HTTP, CONF_HOST: self._host, CONF_TOKEN: self._token},
                )
                vehicles = await client.vehicles()
                if not vehicles:
                    errors["base"] = "no_vehicles"
                else:
                    return self.async_create_entry(
                        title=f"LiAuto CLI ({self._host})",
                        data={
                            CONF_MODE: MODE_HTTP,
                            CONF_HOST: self._host,
                            CONF_TOKEN: self._token,
                        },
                    )
            except Exception as err:
                _LOGGER.error("HTTP validation failed: %s", err)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id=STEP_HTTP,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._host): str,
                    vol.Optional(CONF_TOKEN, default=self._token): str,
                }
            ),
            errors=errors,
        )

    async def async_step_local_reuse(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Local mode: reuse existing config or re-auth."""
        if user_input is not None:
            choice = user_input.get("choice", "reuse")
            if choice == "reuse":
                # Try to list vehicles with existing credentials
                try:
                    client = LicliClient(
                        self.hass,
                        {CONF_MODE: MODE_LOCAL, CONF_ACTIVATION_CODE: ""},
                    )
                    vehicles = await client.vehicles()
                    if vehicles:
                        return self.async_create_entry(
                            title="LiAuto CLI (local)",
                            data={CONF_MODE: MODE_LOCAL, CONF_ACTIVATION_CODE: ""},
                        )
                    return self.async_show_form(
                        step_id=STEP_LOCAL_REUSE,
                        errors={"base": "no_vehicles_reuse"},
                    )
                except Exception as err:
                    _LOGGER.error("Reuse check failed: %s", err)
                    return self.async_show_form(
                        step_id=STEP_LOCAL_REUSE,
                        errors={"base": "cannot_reuse"},
                    )
            return await self.async_step_local_activate()

        return self.async_show_form(
            step_id=STEP_LOCAL_REUSE,
            data_schema=vol.Schema(
                {
                    vol.Required("choice", default="reuse"): vol.In(
                        {"reuse": "Reuse existing config", "reauth": "Re-authorize"}
                    ),
                }
            ),
        )

    async def async_step_local_activate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Local mode: enter activation code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._code = user_input.get(CONF_ACTIVATION_CODE, "")
            try:
                await async_activate(self.hass, self._code)
                return await self.async_step_local_auth()
            except Exception as err:
                _LOGGER.error("Activation failed: %s", err)
                errors["base"] = "activate_failed"

        return self.async_show_form(
            step_id=STEP_LOCAL_ACTIVATE,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACTIVATION_CODE): str,
                }
            ),
            errors=errors,
        )

    async def async_step_local_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Local mode: start OAuth login."""
        self._login_session = LicliLoginSession(self.hass, self._code or None)
        try:
            auth_url = await self._login_session.async_start()
        except Exception as err:
            _LOGGER.error("Login start failed: %s", err)
            return self.async_show_form(
                step_id=STEP_LOCAL_AUTH,
                errors={"base": "login_start_failed"},
            )

        return self.async_show_form(
            step_id=STEP_LOCAL_AUTH,
            description_placeholders={"auth_url": auth_url},
        )

    async def async_step_local_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Local mode: paste token JSON."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token_json = user_input.get("token_json", "")
            try:
                if self._login_session is None:
                    raise LicliError("session expired")
                await self._login_session.async_submit(token_json)
                return self.async_create_entry(
                    title="LiAuto CLI (local)",
                    data={CONF_MODE: MODE_LOCAL, CONF_ACTIVATION_CODE: self._code},
                )
            except Exception as err:
                _LOGGER.error("Token submit failed: %s", err)
                errors["base"] = "token_invalid"

        return self.async_show_form(
            step_id=STEP_LOCAL_TOKEN,
            data_schema=vol.Schema(
                {
                    vol.Required("token_json"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entry point: redirect to mode selection."""
        return await self.async_step_mode()
