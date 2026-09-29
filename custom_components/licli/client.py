"""LiAuto CLI client (HTTP and local modes)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant

from .const import CONF_MODE, CONF_HOST, CONF_TOKEN, CONF_ACTIVATION_CODE
from .const import MODE_HTTP, MODE_LOCAL

_LOGGER = logging.getLogger(__name__)


class LicliClient:
    """Client for LiAuto CLI."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize client."""
        self._hass = hass
        self._mode = config[CONF_MODE]
        self._host = config.get(CONF_HOST, f"http://127.0.0.1:18001")
        self._token = config.get(CONF_TOKEN)
        self._code = config.get(CONF_ACTIVATION_CODE)

    async def _http_request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make HTTP request to licli serve."""
        url = f"{self._host.rstrip('/')}{path}"
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, url, headers=headers, json=json_data
            ) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    error = data.get("error", {})
                    raise LicliError(error.get("message", "Unknown error"))
                return data

    async def _cli_request(self, args: list[str]) -> dict[str, Any]:
        """Run liauto CLI via `python -m liauto` (installed as HA requirement)."""
        # Non-serve mode: keep licli credentials/config inside HA's .storage/licli.
        # licli follows XDG, so XDG_CONFIG_HOME=<config_dir>/.storage puts
        # device.json/auth.json under <config_dir>/.storage/licli/.
        config_dir = self._hass.config.config_dir
        xdg_config_home = os.path.join(config_dir, ".storage")

        env = os.environ.copy()
        env["XDG_CONFIG_HOME"] = xdg_config_home
        if self._code:
            env["LICLI_CODE"] = self._code

        cmd = [sys.executable, "-m", "liauto"] + args + ["--json"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except OSError as err:
            raise LicliError(f"failed to start liauto: {err}") from err

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            _LOGGER.error("licli stderr: %s", stderr.decode())
            raise LicliError(f"licli exited {proc.returncode}")

        out = stdout.decode().strip()
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            # Some control commands print human text (e.g. "trunk open sent (operationId: ...)")
            return {"ok": True, "raw": out}

    async def vehicles(self) -> list[dict[str, Any]]:
        """List vehicles."""
        if self._mode == MODE_HTTP:
            data = await self._http_request("GET", "/vehicles")
        else:
            data = await self._cli_request(["vehicles"])
        return data.get("vehicles", [])

    async def status(self, vin: str) -> dict[str, Any]:
        """Get vehicle status."""
        if self._mode == MODE_HTTP:
            data = await self._http_request("GET", f"/vehicles/{vin}/status")
        else:
            data = await self._cli_request(["status", vin])
        return data.get("state", {})

    async def location(self, vin: str) -> dict[str, Any] | None:
        """Get vehicle location."""
        if self._mode == MODE_HTTP:
            data = await self._http_request("GET", f"/vehicles/{vin}/status")
        else:
            data = await self._cli_request(["status", vin])
        return data.get("location")

    async def control(self, vin: str, action: str, **kwargs: Any) -> dict[str, Any]:
        """Send control command."""
        body = {"action": action}
        body.update({k: v for k, v in kwargs.items() if v is not None})

        if self._mode == MODE_HTTP:
            return await self._http_request(
                "POST", f"/vehicles/{vin}/control", body
            )
        else:
            # Map HA action names to CLI subcommands. -yes must come right
            # after "control" for actions that require confirmation (trunk).
            needs_yes = action == "trunk"
            action_map = {
                "lock": ["lock"],
                "unlock": ["unlock"],
                "find": ["find"],
                "wake": ["wake"],
                "ac_on": ["ac", "on"],
                "ac_off": ["ac", "off"],
                "ac_auto": ["ac", "auto"],
                "ac_temp": ["ac", "temp", str(kwargs.get("temp", 24))],
                "ac_fast_cool": ["ac", "fast-cool"],
                "ac_fast_heat": ["ac", "fast-heat"],
                "trunk": ["trunk", "open" if kwargs.get("open") else "close"],
                "result": ["result", str(kwargs.get("request_id", ""))],
            }
            sub = action_map.get(action, [action])
            cmd = ["control"]
            if needs_yes:
                cmd.append("-yes")
            cmd += [vin] + sub
            return await self._cli_request(cmd)


class LicliError(Exception):
    """LiAuto CLI error."""
