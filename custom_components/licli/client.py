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
        self._login_proc: asyncio.subprocess.Process | None = None

    def _base_env(self) -> dict[str, str]:
        """Build subprocess env: licli config lives in HA's .storage/licli."""
        config_dir = self._hass.config.config_dir
        env = os.environ.copy()
        env["XDG_CONFIG_HOME"] = os.path.join(config_dir, ".storage")
        if self._code:
            env["LICLI_CODE"] = self._code
        return env

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
        cmd = [sys.executable, "-m", "liauto"] + args + ["--json"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._base_env(),
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


async def async_activate(hass: HomeAssistant, code: str) -> dict[str, Any]:
    """Run `liauto activate` with the given activation code."""
    client = LicliClient(hass, {CONF_MODE: MODE_LOCAL, CONF_ACTIVATION_CODE: code})
    return await client._cli_request(["activate"])


class LicliLoginSession:
    """Interactive `liauto login` session kept alive across config-flow steps."""

    def __init__(self, hass: HomeAssistant, code: str | None) -> None:
        self._hass = hass
        self._code = code or None
        self._proc: asyncio.subprocess.Process | None = None

    async def async_start(self) -> str:
        """Start login and return the OAuth authorization URL."""
        client = LicliClient(self._hass, {CONF_MODE: MODE_LOCAL, CONF_ACTIVATION_CODE: self._code})
        self._proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "liauto",
            "login",
            "--json",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=client._base_env(),
        )
        line = await self._proc.stdout.readline()
        payload = json.loads(line.decode().strip() or "{}")
        url = payload.get("auth_url")
        if not url:
            raise LicliError(payload.get("error", {}).get("message", "no auth_url"))
        return url

    async def async_submit(self, token_json: str) -> dict[str, Any]:
        """Feed the pasted token JSON to the login process and finish."""
        if self._proc is None or self._proc.stdin is None:
            raise LicliError("login session not started")
        self._proc.stdin.write((token_json.strip() + "\n").encode())
        await self._proc.stdin.drain()
        stdout, stderr = await self._proc.communicate()
        lines = [ln for ln in stdout.decode().strip().splitlines() if ln.strip()]
        if not lines:
            raise LicliError(stderr.decode().strip() or "login failed")
        payload = json.loads(lines[-1])
        if not payload.get("ok"):
            raise LicliError(payload.get("error", {}).get("message", "login failed"))
        return payload
