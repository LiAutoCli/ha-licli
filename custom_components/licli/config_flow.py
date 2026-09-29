"""Config flow for LiAuto CLI integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
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
from .client import LicliClient, LicliLoginSession, LicliError

_LOGGER = logging.getLogger(__name__)

STEP_MODE = "mode"
STEP_HTTP = "http"
STEP_LOCAL = "local"
STEP_LOCAL_ACTION = "local_action"
STEP_LOCAL_REUSE = "local_reuse"
STEP_LOCAL_REAUTH = "local_reauth"
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
        self._auth_url: str | None = None
        self._reuse_error: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entry point: redirect to mode selection."""
        return await self.async_step_mode()

    async def async_step_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose connection mode (menu)."""
        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            if self._mode == MODE_HTTP:
                return await self.async_step_http()
            return await self.async_step_local()

        return self.async_show_menu(
            step_id=STEP_MODE,
            menu_options=[MODE_HTTP, MODE_LOCAL],
        )

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
            except Exception as err:  # noqa: BLE001
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

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Local mode: collect the activation code (required for status/control)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = (user_input.get(CONF_ACTIVATION_CODE) or "").strip()
            if not code:
                errors["base"] = "code_required"
            else:
                self._code = code
                return await self.async_step_local_action()

        if self._reuse_error:
            errors["base"] = self._reuse_error
            self._reuse_error = None

        return self.async_show_form(
            step_id=STEP_LOCAL,
            data_schema=vol.Schema({vol.Required(CONF_ACTIVATION_CODE): str}),
            errors=errors,
        )

    async def async_step_local_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Local mode: reuse existing config or re-authorize (menu)."""
        return self.async_show_menu(
            step_id=STEP_LOCAL_ACTION,
            menu_options=[STEP_LOCAL_REUSE, STEP_LOCAL_REAUTH],
        )

    async def async_step_local_reuse(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reuse credentials already in .storage/licli, validating the code."""
        try:
            client = LicliClient(
                self.hass,
                {CONF_MODE: MODE_LOCAL, CONF_ACTIVATION_CODE: self._code},
            )
            vehicles = await client.vehicles()
            if not vehicles:
                self._reuse_error = "no_vehicles_reuse"
            else:
                # `status` requires a valid activation code -> validates it too.
                await client.status(vehicles[0]["vin"])
                return self.async_create_entry(
                    title="LiAuto CLI (local)",
                    data={CONF_MODE: MODE_LOCAL, CONF_ACTIVATION_CODE: self._code},
                )
        except LicliError as err:
            _LOGGER.error("Reuse validation failed: %s", err)
            self._reuse_error = (
                "invalid_code" if "licen" in str(err).lower() else "cannot_reuse"
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Reuse validation failed: %s", err)
            self._reuse_error = "cannot_reuse"

        return await self.async_step_local()

    async def async_step_local_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-authorize: start OAuth login and show the authorization URL."""
        if user_input is not None:
            return await self.async_step_local_token()

        if self._login_session is None:
            self._login_session = LicliLoginSession(self.hass, self._code or None)
            try:
                self._auth_url = await self._login_session.async_start()
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Login start failed: %s", err)
                self._login_session = None
                self._reuse_error = "login_start_failed"
                return await self.async_step_local()

        return self.async_show_form(
            step_id=STEP_LOCAL_REAUTH,
            data_schema=vol.Schema({vol.Optional("confirm", default=True): bool}),
            description_placeholders={"auth_url": self._auth_url or ""},
        )

    async def async_step_local_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Local mode: paste the token JSON returned after login."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                if self._login_session is None:
                    raise LicliError("session expired")
                await self._login_session.async_submit(user_input.get("token_json", ""))
                return self.async_create_entry(
                    title="LiAuto CLI (local)",
                    data={CONF_MODE: MODE_LOCAL, CONF_ACTIVATION_CODE: self._code},
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Token submit failed: %s", err)
                errors["base"] = "token_invalid"

        return self.async_show_form(
            step_id=STEP_LOCAL_TOKEN,
            data_schema=vol.Schema({vol.Required("token_json"): str}),
            errors=errors,
        )
