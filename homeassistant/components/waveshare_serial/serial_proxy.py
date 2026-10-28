"""Home Assistant-aware Waveshare serial proxy transport for serialx."""

import asyncio
from collections.abc import Callable
from typing import cast, override

from pywaveshare import (
    InvalidSettingsError,
    WaveshareClient,
    WaveshareSerial,
    WaveshareSerialTransport,
)
from serialx import BaseSerial, BaseSerialTransport, register_uri_handler
from yarl import URL

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, async_get_hass
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

_HASS_LOOP: asyncio.AbstractEventLoop | None = None


def build_url(entry_id: str, instance: int) -> URL:
    """Build a stable URL for a configured serial proxy port."""
    return URL.build(
        scheme="waveshare-hass",
        host="waveshare",
        path=f"/{entry_id}/{instance}",
    )


async def _resolve_client(entry_id: str) -> WaveshareClient:
    """Resolve a loaded config entry on the Home Assistant event loop."""
    hass: HomeAssistant = async_get_hass()
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise InvalidSettingsError(f"No Waveshare config entry with id {entry_id!r}")
    if entry.state is not ConfigEntryState.LOADED:
        raise ConfigEntryNotReady(f"Waveshare config entry {entry_id!r} is not loaded")
    return cast(WaveshareClient, entry.runtime_data.client)


class HassWaveshareSerial(WaveshareSerial):
    """Resolve the config entry's shared client before opening a serial port."""

    @override
    async def _async_open(self) -> None:
        if self._client is None:
            parsed = URL(str(self._path))
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 2 or not parts[0] or not parts[1].isdecimal():
                raise InvalidSettingsError(
                    f"Invalid Waveshare serial proxy URL {self._path!r}"
                )
            if _HASS_LOOP is None:
                raise InvalidSettingsError(
                    "Waveshare integration has not registered its event loop"
                )
            self._client = await asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(_resolve_client(parts[0]), _HASS_LOOP)
            )
            self._instance_id = int(parts[1])
            self._client_loop = self._client.loop
        await super()._async_open()


class HassWaveshareSerialTransport(WaveshareSerialTransport):
    """Construct the Home Assistant-aware serial implementation."""

    transport_name = "waveshare-hass"
    _serial_cls = HassWaveshareSerial


def register_serialx_transport(loop: asyncio.AbstractEventLoop) -> Callable[[], None]:
    """Register the serialx URI handler until Home Assistant stops."""
    global _HASS_LOOP  # noqa: PLW0603  # pylint: disable=global-statement
    _HASS_LOOP = loop
    unregister = register_uri_handler(
        scheme="waveshare-hass://",
        unique_scheme="waveshare-hass-internal://",
        sync_cls=cast(type[BaseSerial], HassWaveshareSerial),
        async_transport_cls=cast(
            type[BaseSerialTransport], HassWaveshareSerialTransport
        ),
    )

    def unregister_transport() -> None:
        global _HASS_LOOP  # noqa: PLW0603  # pylint: disable=global-statement
        unregister()
        _HASS_LOOP = None

    return unregister_transport
