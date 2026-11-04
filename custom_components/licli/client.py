"""LiAuto CLI client (HTTP and local modes)."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
import os
import sys
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import CONF_MODE, CONF_HOST, CONF_TOKEN, CONF_ACTIVATION_CODE
from .const import MODE_HTTP, MODE_LOCAL, CONFIRM_ACTIONS

_LOGGER = logging.getLogger(__name__)


def _pic_time_to_ms(value: Any) -> int | None:
    """Convert a ``picTime`` value to epoch milliseconds.

    Two shapes are seen in the wild:

    * ``"2026-10-10T02:45:09Z"`` - ISO 8601 with a UTC offset (M platform)
    * ``"2026-10-10 08:53:25"`` - naive local wall clock, no offset (X platform)

    Naive values are interpreted in Home Assistant's local timezone.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None

    text = value.strip()
    parsed = dt_util.parse_datetime(text)
    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return int(parsed.timestamp() * 1000)


def _timestamp_ms(data: dict[str, Any]) -> int | None:
    """Return the photo capture time in epoch milliseconds.

    Prefers the numeric ``timestamp`` field and falls back to ``picTime``
    only (``picTimestamp`` is intentionally ignored).
    """
    if (timestamp := data.get("timestamp")) is not None:
        return timestamp
    return _pic_time_to_ms(data.get("picTime"))


# Upstream sometimes uses INT32_MIN as a "no value" sentinel for numeric fields.
_SENTINEL = -2147483648


def _normalize(value: Any) -> Any:
    """Replace the upstream INT32_MIN sentinel with None, recursively."""
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value == _SENTINEL:
        return None
    return value


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
                return _normalize(data)

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
            # The licli CLI prints a structured error envelope to **stdout**
            # (even on failure) and leaves stderr empty, e.g.
            #   {"ok":false,"error":{"code":"command_failed","message":"...","retryable":false}}
            # Older code only logged stderr, so every failure looked like a
            # bare "licli exited 1" with no reason. Surface stdout JSON too.
            out = stdout.decode().strip()
            payload: dict[str, Any] = {}
            if out:
                try:
                    payload = json.loads(out)
                except json.JSONDecodeError:
                    payload = {}
            err = payload.get("error") or {}
            code = err.get("code")
            message = err.get("message")
            retryable = err.get("retryable")
            detail = message or out or stderr.decode().strip() or "(no output)"
            _LOGGER.error(
                "licli %s failed (exit %s): code=%s retryable=%s: %s",
                " ".join(args),
                proc.returncode,
                code,
                retryable,
                detail,
            )
            raise LicliError(
                f"licli exited {proc.returncode}: {detail}",
                code=code,
                retryable=retryable,
            )

        out = stdout.decode().strip()
        try:
            return _normalize(json.loads(out))
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

    async def tire(self, vin: str) -> dict[str, Any]:
        """Get tyre pressures/temperatures (requires liauto>=0.1.1b3).

        CLI: `licli tire <vin> --json` -> {"tires": {...}}
        HTTP: GET /vehicles/<vin>/tire
        """
        if self._mode == MODE_HTTP:
            data = await self._http_request("GET", f"/vehicles/{vin}/tire")
        else:
            data = await self._cli_request(["tire", vin])
        return data.get("tires") or {}

    async def photos(self, vin: str) -> dict[str, Any]:
        """Get parking photos (requires liauto>=0.1.2b0).

        CLI: `licli photos <vin> --json` -> {"photos": [{"name","url"}], ...}
        Returns the whole payload (photos + timestamp) keyed under "photos"
        and "timestamp" by the caller. We keep the raw payload so the entity
        can read both the photo list and the capture time.
        """
        if self._mode == MODE_HTTP:
            data = await self._http_request("GET", f"/vehicles/{vin}/photos")
        else:
            data = await self._cli_request(["photos", vin])
        return {
            "photos": data.get("photos") or [],
            "timestamp": _timestamp_ms(data),
            "pic_time": data.get("picTime"),
        }

    async def control(self, vin: str, action: str, **kwargs: Any) -> dict[str, Any]:
        """Send control command."""
        body = {"action": action}
        body.update({k: v for k, v in kwargs.items() if v is not None})

        if self._mode == MODE_HTTP:
            return await self._http_request(
                "POST", f"/vehicles/{vin}/control", body
            )
        else:
            # In non-interactive mode licli forces confirmation for some
            # actions (unlock, trunk); they need `-yes` or they exit 1 with
            # "confirmation required in non-interactive mode (use -yes)".
            # Other actions must NOT get -yes. `-yes` is a control-level flag
            # and must sit right after "control".
            needs_yes = action in CONFIRM_ACTIONS
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

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


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
